#!/usr/bin/env bash
set -euo pipefail
ROOT="${HOME}/Applications/Lichii"
REPO="${LICHII_SOURCE:-${ROOT}/source}"
BASE_BRANCH=odin-armadaos
BOX="${LICHII_TOOLBOX:-lichii-debug}"
[[ -d "${REPO}/.git" ]] || { echo "Not a Git checkout: $REPO" >&2; exit 1; }
cd "$REPO"
[[ -z "$(git status --porcelain)" ]] || { echo 'Working tree is not clean; commit or stash your changes first.' >&2; exit 1; }
[[ "$(git branch --show-current)" == "$BASE_BRANCH" ]] || { echo "Switch to $BASE_BRANCH first." >&2; exit 1; }

# Fresh clones use "upstream"; the original Odin checkout uses "origin"
# for zortos293/Lichii. Allow both, but never fetch from an unknown project.
REMOTE=upstream
if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  REMOTE=origin
fi
URL="$(git remote get-url "$REMOTE" 2>/dev/null || true)"
case "$URL" in
  https://github.com/zortos293/Lichii|https://github.com/zortos293/Lichii.git|git@github.com:zortos293/Lichii|git@github.com:zortos293/Lichii.git)
    ;;
  *)
    echo 'STOP: No verified zortos293/Lichii upstream remote found.' >&2
    echo 'Add it with: git remote add upstream https://github.com/zortos293/Lichii.git' >&2
    exit 1
    ;;
esac

CAND="odin-update-$(date +%Y%m%d-%H%M%S)"
BUILD="${ROOT}/build-${CAND}"
git fetch "$REMOTE" nx2
git switch -c "$CAND"
printf '%s\n' "$CAND" > "${ROOT}/latest-candidate-branch.txt"
echo "Created candidate branch $CAND; stable branch left untouched."
# FETCH_HEAD is exactly the branch just fetched, even if remote-tracking names vary.
if ! git merge --no-edit FETCH_HEAD; then
  echo 'Upstream merge needs attention. Do not run promotion. Resolve, test, and commit conflicts on this candidate branch.' >&2
  exit 1
fi
git submodule update --init --recursive
toolbox run --container "$BOX" cmake -S "$REPO" -B "$BUILD" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DYUZU_TESTS=OFF \
  -DVulkanHeaders_FORCE_BUNDLED=ON -DCMAKE_CXX_FLAGS=-Wno-error=shadow
toolbox run --container "$BOX" cmake --build "$BUILD" --parallel 4
[[ -x "${BUILD}/bin/lichii" ]] || { echo 'Candidate executable missing' >&2; exit 1; }
echo "Candidate compiled: $BUILD/bin/lichii"
echo "TEST using: LICHII_BINARY='$BUILD/bin/lichii' '$REPO/scripts/launch-odin.sh'"
echo "If it works in-game, run: '$REPO/scripts/promote-candidate.sh' '$CAND'"

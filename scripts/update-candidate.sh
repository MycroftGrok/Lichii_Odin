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
git remote get-url upstream >/dev/null || { echo 'Missing upstream remote.' >&2; exit 1; }
CAND="odin-update-$(date +%Y%m%d-%H%M%S)"
BUILD="${ROOT}/build-${CAND}"
git fetch upstream nx2
git switch -c "$CAND"
printf '%s\n' "$CAND" > "${ROOT}/latest-candidate-branch.txt"
echo "Created candidate branch $CAND; stable branch left untouched."
if ! git merge --no-edit upstream/nx2; then
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

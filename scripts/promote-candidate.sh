#!/usr/bin/env bash
set -euo pipefail
ROOT="${HOME}/Applications/Lichii"
REPO="${LICHII_SOURCE:-${ROOT}/source}"
CAND="${1:-}"
[[ "$CAND" =~ ^odin-update-[0-9]{8}-[0-9]{6}$ ]] || { echo 'Usage: promote-candidate.sh odin-update-YYYYMMDD-HHMMSS' >&2; exit 1; }
BUILD="${ROOT}/build-${CAND}"
[[ -x "${BUILD}/bin/lichii" ]] || { echo 'Candidate build not found; aborting' >&2; exit 1; }
cd "$REPO"
[[ -z "$(git status --porcelain)" ]] || { echo 'Working tree not clean; aborting' >&2; exit 1; }
[[ "$(git branch --show-current)" == "$CAND" ]] || { echo "Switch to $CAND before promotion" >&2; exit 1; }
read -r -p "Did you personally test this candidate in-game? Type YES: " agree
[[ "$agree" == YES ]] || { echo 'Promotion canceled'; exit 1; }
# Only promote after a fast-forward is possible, so the user's stable branch remains identifiable.
git merge-base --is-ancestor odin-armadaos "$CAND" || { echo 'Candidate diverged from stable; aborting' >&2; exit 1; }
git switch odin-armadaos
git merge --ff-only "$CAND"
mkdir -p "${ROOT}/bin"
TARGET="${ROOT}/bin/lichii-odin"
if [[ -e "$TARGET" || -L "$TARGET" ]]; then
  cp -a "$TARGET" "${TARGET}.previous"
fi
TEMP="${TARGET}.new.$$"
trap 'rm -f "$TEMP"' EXIT
ln -s "${BUILD}/bin/lichii" "$TEMP"
mv -Tf "$TEMP" "$TARGET"
trap - EXIT
echo 'Promoted tested update. Previous launch target retained as lichii-odin.previous.'
echo "Optional push: git push odin-fork odin-armadaos"

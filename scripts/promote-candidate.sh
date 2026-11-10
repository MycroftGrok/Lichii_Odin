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
git merge-base --is-ancestor odin-armadaos "$CAND" || { echo 'Candidate diverged from stable; aborting' >&2; exit 1; }
read -r -p "Did you personally test this candidate in-game? Type YES: " agree
[[ "$agree" == YES ]] || { echo 'Promotion canceled'; exit 1; }

# Back up the actual stable binary before changing source branches or the launcher.
bash "${REPO}/scripts/snapshot-stable.sh"

# Keep the tested output independent of future builds to this candidate directory.
mkdir -p "${ROOT}/bin" "${ROOT}/releases"
RELEASE_DIR="$(mktemp -d "${ROOT}/releases/odin-promotion-XXXXXXXX")"
RELEASE="${RELEASE_DIR}/lichii"
cp -p -- "${BUILD}/bin/lichii" "$RELEASE"
if [[ ! -s "$RELEASE" || ! -x "$RELEASE" ]] || ! cmp -s -- "${BUILD}/bin/lichii" "$RELEASE"; then
  echo 'STOP: Candidate copy failed verification; stable launcher unchanged.' >&2
  exit 1
fi

git switch odin-armadaos
git merge --ff-only "$CAND"
TARGET="${ROOT}/bin/lichii-odin"
TEMP="${TARGET}.new.$$"
trap 'rm -f -- "$TEMP"' EXIT
ln -s -- "$RELEASE" "$TEMP"
mv -Tf -- "$TEMP" "$TARGET"
trap - EXIT
echo "Promoted tested binary from $CAND"
echo "Independent previous executable available via ${TARGET}.previous"
echo "Optional push: git push odin-fork odin-armadaos"

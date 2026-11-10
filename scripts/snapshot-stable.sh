#!/usr/bin/env bash
# Preserve the actual stable executable before a new build or candidate promotion.
# Optional argument: path to the binary that the next build may overwrite.
set -euo pipefail
ROOT="${HOME}/Applications/Lichii"
TARGET="${ROOT}/bin/lichii-odin"
REBUILD_PATH="${1:-}"

if [[ ! -e "$TARGET" && ! -L "$TARGET" ]]; then
  echo "No installed stable executable to snapshot (fresh installation)."
  exit 0
fi
if [[ ! -f "$TARGET" || ! -x "$TARGET" ]]; then
  echo "STOP: Existing stable executable is missing or not executable: $TARGET" >&2
  exit 1
fi

mkdir -p "${ROOT}/backups"
SNAP_DIR="$(mktemp -d "${ROOT}/backups/lichii-odin-XXXXXXXX")"
SNAP="${SNAP_DIR}/lichii"
cp -pL -- "$TARGET" "$SNAP"
if [[ ! -s "$SNAP" || ! -x "$SNAP" ]] || ! cmp -s -- "$TARGET" "$SNAP"; then
  echo "STOP: Backup verification failed; the stable launcher has not been changed." >&2
  exit 1
fi

# Keep .previous as an independent binary, not a link into a mutable build tree.
PREV_TMP="${TARGET}.previous.tmp.$$"
trap 'rm -f -- "$PREV_TMP"' EXIT
ln -s -- "$SNAP" "$PREV_TMP"
mv -Tf -- "$PREV_TMP" "${TARGET}.previous"
trap - EXIT
echo "Saved independent executable backup: $SNAP"

# A rebuild must never modify the file that the stable launcher is currently using.
if [[ -n "$REBUILD_PATH" ]] && [[ "$(realpath -e -- "$TARGET")" == "$(realpath -m -- "$REBUILD_PATH")" ]]; then
  TARGET_TMP="${TARGET}.tmp.$$"
  trap 'rm -f -- "$TARGET_TMP"' EXIT
  ln -s -- "$SNAP" "$TARGET_TMP"
  mv -Tf -- "$TARGET_TMP" "$TARGET"
  trap - EXIT
  echo "Protected stable launcher before rebuilding its former target."
fi

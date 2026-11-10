#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${HOME}/Applications/Lichii"
BINARY="${LICHII_BINARY:-${APP_ROOT}/bin/lichii-odin}"
CONTAINER="${LICHII_TOOLBOX:-lichii-debug}"
ICD="/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json"
if [[ ! -x "$BINARY" ]]; then
  echo "Lichii executable not found: $BINARY" >&2
  echo 'Run scripts/build-deploy.sh or install the preserved milestone.' >&2
  exit 1
fi
if ! command -v toolbox >/dev/null 2>&1; then
  echo 'This launcher requires Fedora toolbox on ArmadaOS.' >&2
  exit 1
fi
exec toolbox run --container "$CONTAINER" env \
  QT_QPA_PLATFORM=wayland \
  VK_DRIVER_FILES="$ICD" \
  "$BINARY" "$@"

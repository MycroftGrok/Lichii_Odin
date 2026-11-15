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

# BEGIN LICHII LSFG AUTO-RECOVERY
# Only restore a missing DLL from the user's own Steam installation.
# Never overwrite an existing DLL or modify Steam itself.
LSFG_DIR="${HOME}/.local/share/lichii/lossless"
LSFG_DST="${LSFG_DIR}/Lossless.dll"
LSFG_SRC="${HOME}/.local/share/Steam/steamapps/common/Lossless Scaling/Lossless.dll"

if [[ ! -e "$LSFG_DST" && ! -L "$LSFG_DST" &&
      -f "$LSFG_SRC" && ! -L "$LSFG_SRC" ]]; then
  if [[ "$(head -c 2 -- "$LSFG_SRC")" == "MZ" ]]; then
    if mkdir -p -- "$LSFG_DIR"; then
      if LSFG_TMP="$(mktemp "$LSFG_DIR/.Lossless.dll.XXXXXXXX")"; then
        if cp -- "$LSFG_SRC" "$LSFG_TMP" &&
           cmp -s -- "$LSFG_SRC" "$LSFG_TMP"; then
          chmod 0644 "$LSFG_TMP"
          if ln -- "$LSFG_TMP" "$LSFG_DST"; then
            echo "PASS: Restored Lossless.dll from Steam for Lichii."
          fi
        else
          echo "WARNING: Could not verify Lossless.dll copy." >&2
        fi
        rm -f -- "$LSFG_TMP"
      fi
    fi
  else
    echo "WARNING: Steam Lossless.dll has an invalid header." >&2
  fi
fi
# END LICHII LSFG AUTO-RECOVERY

exec toolbox run --container "$CONTAINER" env \
  QT_QPA_PLATFORM=wayland \
  VK_DRIVER_FILES="$ICD" \
  "$BINARY" "$@"

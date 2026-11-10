#!/usr/bin/env bash
set -euo pipefail
ROOT="${HOME}/Applications/Lichii"
SOURCE="${LICHII_SOURCE:-${ROOT}/source}"
BUILD="${LICHII_BUILD:-${ROOT}/build-odin-armadaos}"
BOX="${LICHII_TOOLBOX:-lichii-debug}"
TARGET="${ROOT}/bin/lichii-odin"
[[ -f "${SOURCE}/CMakeLists.txt" ]] || { echo "Missing source: $SOURCE" >&2; exit 1; }
command -v toolbox >/dev/null || { echo 'toolbox is required' >&2; exit 1; }
# Never delete src, an existing build, or the user's original AppImage.
if [[ ! -f "${BUILD}/CMakeCache.txt" ]]; then
  toolbox run --container "$BOX" cmake -S "$SOURCE" -B "$BUILD" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DYUZU_TESTS=OFF \
    -DVulkanHeaders_FORCE_BUNDLED=ON -DCMAKE_CXX_FLAGS=-Wno-error=shadow
fi
toolbox run --container "$BOX" cmake --build "$BUILD" --parallel 4
[[ -x "$BUILD/bin/lichii" ]] || { echo 'Build reported success but binary is missing' >&2; exit 1; }
mkdir -p "${ROOT}/bin"
if [[ -e "$TARGET" || -L "$TARGET" ]]; then
  cp -a "$TARGET" "${TARGET}.previous"
  echo "Previous launch target saved to ${TARGET}.previous"
fi
TEMP="${TARGET}.new.$$"
trap 'rm -f "$TEMP"' EXIT
ln -s "$BUILD/bin/lichii" "$TEMP"
mv -Tf "$TEMP" "$TARGET"
trap - EXIT
echo "Installed launch link ${TARGET} -> ${BUILD}/bin/lichii"
echo "Launch with: ${SOURCE}/scripts/launch-odin.sh"

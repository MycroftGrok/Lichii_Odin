#!/usr/bin/env bash
set -euo pipefail
ROOT="${HOME}/Applications/Lichii"
SOURCE="${LICHII_SOURCE:-${ROOT}/source}"
BUILD="${LICHII_BUILD:-${ROOT}/build-odin-armadaos}"
BOX="${LICHII_TOOLBOX:-lichii-debug}"
TARGET="${ROOT}/bin/lichii-odin"
[[ -f "${SOURCE}/CMakeLists.txt" ]] || { echo "Missing source: $SOURCE" >&2; exit 1; }
[[ -f "${SOURCE}/scripts/snapshot-stable.sh" ]] || { echo "Missing backup helper in source checkout" >&2; exit 1; }
command -v toolbox >/dev/null || { echo 'toolbox is required' >&2; exit 1; }

# Snapshot BEFORE the build. If this build would overwrite the current stable
# executable, park the stable launcher on its verified snapshot first.
bash "${SOURCE}/scripts/snapshot-stable.sh" "${BUILD}/bin/lichii"

# Never delete src, an existing build, or the original AppImage.
if [[ ! -f "${BUILD}/CMakeCache.txt" ]]; then
  toolbox run --container "$BOX" cmake -S "$SOURCE" -B "$BUILD" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DYUZU_TESTS=OFF \
    -DVulkanHeaders_FORCE_BUNDLED=ON -DCMAKE_CXX_FLAGS=-Wno-error=shadow
fi
toolbox run --container "$BOX" cmake --build "$BUILD" --parallel 4
[[ -x "$BUILD/bin/lichii" ]] || { echo 'Build reported success but binary is missing' >&2; exit 1; }

# Install an immutable copy, never a direct symlink to an incrementally rebuilt output.
mkdir -p "${ROOT}/bin" "${ROOT}/releases"
RELEASE_DIR="$(mktemp -d "${ROOT}/releases/odin-build-XXXXXXXX")"
RELEASE="${RELEASE_DIR}/lichii"
cp -p -- "$BUILD/bin/lichii" "$RELEASE"
if [[ ! -s "$RELEASE" || ! -x "$RELEASE" ]] || ! cmp -s -- "$BUILD/bin/lichii" "$RELEASE"; then
  echo 'STOP: Compiled executable copy failed verification; stable launcher unchanged.' >&2
  exit 1
fi
TEMP="${TARGET}.new.$$"
trap 'rm -f -- "$TEMP"' EXIT
ln -s -- "$RELEASE" "$TEMP"
mv -Tf -- "$TEMP" "$TARGET"
trap - EXIT
echo "Installed immutable executable: $RELEASE"
echo "Stable launcher: $TARGET"
echo "Previous independent binary: ${TARGET}.previous (if a stable version existed)"
echo "Launch with: ${SOURCE}/scripts/launch-odin.sh"

#!/usr/bin/env bash
set -euo pipefail
REPO="${HOME}/Applications/Lichii/source"
BOX="${LICHII_TOOLBOX:-lichii-debug}"
[[ "$(uname -m)" == aarch64 ]] || { echo 'This installer targets ARM64 (aarch64) devices.' >&2; exit 1; }
[[ -f "${REPO}/CMakeLists.txt" ]] || { echo 'Clone the published odin-armadaos GitHub branch first; README has commands.' >&2; exit 1; }
command -v toolbox >/dev/null || { echo 'Install toolbox on the host before proceeding.' >&2; exit 1; }
if ! toolbox list --containers 2>/dev/null | grep -q "$BOX"; then
  echo "Creating toolbox $BOX for Fedora ARM64"
  toolbox create --container "$BOX" --image registry.fedoraproject.org/fedora-toolbox:44
fi
# Dependencies are installed INSIDE the toolbox only; never mutate bootc host packages.
# RPM Fusion may be necessary for ffmpeg-devel on some Fedora images.
toolbox run --container "$BOX" sudo dnf install -y \
  git cmake ninja-build gcc gcc-c++ python3 pkgconf-pkg-config \
  autoconf libtool glslang glslang-devel fmt-devel boost-devel \
  SDL3-devel vulkan-headers vulkan-loader-devel mesa-vulkan-drivers \
  spirv-tools-devel spirv-headers-devel libusb1-devel \
  lz4-devel libzstd-devel openssl-devel zlib-ng-compat-devel \
  nlohmann-json-devel qt6-qtbase-devel qt6-qtbase-private-devel \
  qt6-qtwayland qt6-qtmultimedia-devel qt6-qtcharts-devel \
  opus-devel ffmpeg-free-devel
bash "${REPO}/scripts/build-deploy.sh"
bash "${REPO}/scripts/install-launcher.sh"
echo 'Launcher installed. Set InputPlumber target to xbox-elite if SDL3 detects no gamepad.'
echo 'Vulkan check after game launches: grep "Report: Device:" ~/.local/share/eden/log/eden_log.txt | tail -1'

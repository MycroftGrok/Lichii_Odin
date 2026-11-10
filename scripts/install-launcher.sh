#!/usr/bin/env bash
set -euo pipefail
ROOT="${HOME}/Applications/Lichii"
SCRIPT="${ROOT}/source/scripts/launch-odin.sh"
TARGET="${ROOT}/bin/lichii-odin"
[[ -x "$SCRIPT" ]] || { echo "Launch script not found: $SCRIPT" >&2; exit 1; }
[[ -x "$TARGET" ]] || { echo "Executable link not found: $TARGET" >&2; exit 1; }
mkdir -p "${HOME}/.local/bin" "${HOME}/.local/share/applications"
cp -p "$SCRIPT" "${HOME}/.local/bin/lichii-odin"
cat > "${HOME}/.local/share/applications/lichii-odin.desktop" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Lichii (Odin ARM64)
Comment=Lichii with ArmadaOS Wayland and hardware Vulkan
Exec=${HOME}/.local/bin/lichii-odin
Terminal=false
Categories=Game;Emulator;
DESKTOP
echo "KDE launcher installed: ${HOME}/.local/share/applications/lichii-odin.desktop"

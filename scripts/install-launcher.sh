#!/usr/bin/env bash
# Refresh both KDE desktop and Games menu shortcuts without rebuilding or switching Lichii.
set -euo pipefail
ROOT="${HOME}/Applications/Lichii"
SCRIPT="${ROOT}/source/scripts/launch-odin.sh"
TARGET="${ROOT}/bin/lichii-odin"
LAUNCHER="${HOME}/.local/bin/lichii-odin"
MENU="${HOME}/.local/share/applications/lichii-odin.desktop"

[[ -f "$SCRIPT" ]] || { echo "Launch script not found: $SCRIPT" >&2; exit 1; }
[[ -x "$TARGET" ]] || { echo "Working Lichii executable not found: $TARGET" >&2; exit 1; }
mkdir -p "${HOME}/.local/bin" "${HOME}/.local/share/applications"
cp -p "$SCRIPT" "$LAUNCHER"
chmod +x "$LAUNCHER"

ICON=applications-games
if [[ -f "${ROOT}/source/dist/lichii.png" ]]; then
    ICON="${ROOT}/source/dist/lichii.png"
fi
cat > "$MENU" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Lichii (Odin ARM64)
GenericName=Switch Emulator
Comment=Lichii with ArmadaOS native Wayland and hardware Vulkan
Exec=$LAUNCHER
Icon=$ICON
Terminal=false
Categories=Game;Emulator;
Keywords=Nintendo;Switch;Lichii;Odin;
StartupNotify=true
DESKTOP
chmod +x "$MENU"

DESKTOP_DIR="${HOME}/Desktop"
if command -v xdg-user-dir >/dev/null 2>&1; then
    DETECTED="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
    if [[ -n "$DETECTED" && "$DETECTED" != "$HOME" ]]; then
        DESKTOP_DIR="$DETECTED"
    fi
fi
mkdir -p "$DESKTOP_DIR"
cp "$MENU" "$DESKTOP_DIR/lichii-odin.desktop"
chmod +x "$DESKTOP_DIR/lichii-odin.desktop"
if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 >/dev/null 2>&1 || true
fi

echo "PASS: Games menu shortcut: $MENU"
echo "PASS: Desktop shortcut: $DESKTOP_DIR/lichii-odin.desktop"
echo "PASS: Existing stable emulator remains: $(readlink -f "$TARGET")"

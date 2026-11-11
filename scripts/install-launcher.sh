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

# Steam ROM shortcut integration uses a separate wrapper and never changes
# the verified Lichii launcher or active executable.
STEAM_HELPER="${ROOT}/source/scripts/steam-integration.py"
[[ -f "$STEAM_HELPER" ]] || { echo "Missing Steam integration helper: $STEAM_HELPER" >&2; exit 1; }
mkdir -p "$HOME/.local/share/lichii/tools"
cp -p "$STEAM_HELPER" "$HOME/.local/share/lichii/tools/steam-integration.py"
cp -p "$ROOT/source/scripts/steam_artwork.py" "$HOME/.local/share/lichii/tools/steam_artwork.py"
cat > "$HOME/.local/bin/lichii-steam-game" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 || ! -f "$1" ]]; then
    echo "Expected one existing ROM file path" >&2
    exit 1
fi
exec "$HOME/.local/bin/lichii-odin" -f -g "$1"
WRAPPER
chmod +x "$HOME/.local/bin/lichii-steam-game"

STEAM_MENU="$HOME/.local/share/applications/lichii-steam-integration.desktop"
cat > "$STEAM_MENU" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Steam Integration
GenericName=Import Lichii ROMs into Steam
Comment=Import Switch and Switch 2 ROMs into Steam collections without duplicates
Exec=konsole --hold -e /usr/bin/python3 $HOME/.local/share/lichii/tools/steam-integration.py --mode all
Icon=steam
Terminal=false
Categories=Game;Utility;
Keywords=Steam;Lichii;Switch;Switch2;
DESKTOP
chmod +x "$STEAM_MENU"
echo "PASS: Games menu shortcut 'Steam Integration': $STEAM_MENU"

echo "PASS: Desktop shortcut: $DESKTOP_DIR/lichii-odin.desktop"
echo "PASS: Existing stable emulator remains: $(readlink -f "$TARGET")"

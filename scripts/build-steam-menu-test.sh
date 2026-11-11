#!/usr/bin/env bash
# Build and launch a separate Steam-menu candidate on ArmadaOS ARM64.
# Does not install or promote a candidate, touch source files, or replace Lichii.
set -euo pipefail

ROOT="$HOME/Applications/Lichii"
SOURCE="$ROOT/source"
BUILD="$ROOT/build-steam-menu-test"
STABLE="$ROOT/bin/lichii-odin"
BOX="${LICHII_TOOLBOX:-lichii-debug}"
TEST_LAUNCHER="$HOME/.local/bin/lichii-steam-menu-test"
MENU="$HOME/.local/share/applications/lichii-steam-menu-test.desktop"

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ "$(uname -m)" == aarch64 ]] || fail "This build is for Odin ARM64 (aarch64)."
[[ -d "$SOURCE/.git" ]] || fail "Existing Lichii checkout missing: $SOURCE"
[[ -x "$STABLE" ]] || fail "Working stable Lichii executable missing: $STABLE"
[[ ! -L "$BUILD" ]] || fail "Candidate build directory is a symlink: $BUILD"
command -v toolbox >/dev/null 2>&1 || fail "Fedora toolbox command missing."
command -v git >/dev/null 2>&1 || fail "Git command missing."

cd "$SOURCE"
grep -q 'Configure SteamGridDB API key' src/yuzu/main_window.cpp ||
    fail "Steam menu source is missing; update the odin-steam-preview branch."
[[ -f scripts/steam-integration.py && -f scripts/steam_artwork.py ]] ||
    fail "Steam integration helper files are missing."
[[ -z "$(git status --porcelain)" ]] ||
    fail "Source has uncommitted changes; review them before compiling."

BRANCH="$(git branch --show-current)"
HEAD="$(git rev-parse --short=12 HEAD)"
STABLE_REAL="$(readlink -f "$STABLE")"
case "$STABLE_REAL" in
    "$BUILD"/*) fail "Stable binary is within test build directory." ;;
esac
STABLE_SHA="$(sha256sum "$STABLE" | awk '{print $1}')"

echo "=== BUILD TEST DETAILS ==="
echo "Branch: $BRANCH"
echo "Source revision: $HEAD"
echo "Toolbox: $BOX"
echo "Independent candidate: $BUILD"
echo "Preserving stable binary: $STABLE_REAL"

# Match the prior known-working Fedora toolbox candidate CMake configuration.
# Avoid modifying the old build or the source tree and limit parallelism to 4.
echo "=== CONFIGURE SEPARATE STEAM MENU BUILD ==="
toolbox run --container "$BOX" cmake -S "$SOURCE" -B "$BUILD" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DYUZU_TESTS=OFF \
    -DVulkanHeaders_FORCE_BUNDLED=ON \
    -DCMAKE_CXX_FLAGS=-Wno-error=shadow

echo "=== COMPILE STEAM MENU CANDIDATE ==="
toolbox run --container "$BOX" cmake --build "$BUILD" --target yuzu --parallel 4
[[ -x "$BUILD/bin/lichii" ]] ||
    fail "No executable at $BUILD/bin/lichii after build."

[[ "$(readlink -f "$STABLE")" == "$STABLE_REAL" ]] ||
    fail "Stable binary symlink unexpectedly changed. Nothing auto-repaired."
[[ "$(sha256sum "$STABLE" | awk '{print $1}')" == "$STABLE_SHA" ]] ||
    fail "Stable executable unexpectedly changed. Nothing auto-repaired."
echo "PASS: Original stable binary unchanged (SHA-256 verified)."

mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
# This wrapper overrides the binary only for the test process.
cat > "$TEST_LAUNCHER" <<LAUNCH
#!/usr/bin/env bash
set -euo pipefail
export LICHII_BINARY="$BUILD/bin/lichii"
exec "$SOURCE/scripts/launch-odin.sh" "\$@"
LAUNCH
chmod +x "$TEST_LAUNCHER"

ICON=applications-games
if [[ -f "$SOURCE/dist/lichii.png" ]]; then
    ICON="$SOURCE/dist/lichii.png"
fi
cat > "$MENU" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Lichii (Steam Menu Test)
GenericName=Switch Emulator Test Build
Comment=Separate ARM64 test build with native Steam menu
Exec=$TEST_LAUNCHER
Icon=$ICON
Terminal=false
Categories=Game;Emulator;
Keywords=Lichii;Steam;Switch;Odin;Test;
StartupNotify=true
DESKTOP
chmod +x "$MENU"

DESKTOP_DIR="$HOME/Desktop"
if command -v xdg-user-dir >/dev/null 2>&1; then
    DETECTED="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
    if [[ -n "$DETECTED" && "$DETECTED" != "$HOME" ]]; then
        DESKTOP_DIR="$DETECTED"
    fi
fi
mkdir -p "$DESKTOP_DIR"
cp "$MENU" "$DESKTOP_DIR/lichii-steam-menu-test.desktop"
chmod +x "$DESKTOP_DIR/lichii-steam-menu-test.desktop"
if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 >/dev/null 2>&1 || true
fi

echo
echo "=== STEAM MENU TEST BUILD READY ==="
echo "PASS: Candidate: $BUILD/bin/lichii"
echo "PASS: KDE Games menu: Lichii (Steam Menu Test)"
echo "PASS: Desktop: $DESKTOP_DIR/lichii-steam-menu-test.desktop"
echo "PASS: Original Lichii remained unchanged."
echo
echo "Launch from Games or run:"
echo "  $TEST_LAUNCHER"
echo "Then check Steam > Configure SteamGridDB API key..."
echo "Close Steam before importing or scraping artwork."

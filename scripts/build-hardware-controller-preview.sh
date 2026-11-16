#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# ArmadaOS AArch64 isolated build; never clean or replace working Lichii.
set -Eeuo pipefail
ROOT="$HOME/Applications/Lichii"
SOURCE="$ROOT/source"
BRANCH="feature/startup-hardware-diagnostics-20261112"
BOX="${LICHII_TOOLBOX:-lichii-debug}"
STABLE="$ROOT/bin/lichii-odin"
OLD_PREVIEW="$ROOT/build-steam-menu-test/bin/lichii"
REAL_HOME="$HOME"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
JOBS="${LICHII_BUILD_JOBS:-4}"
LOGDIR="$HOME/.local/share/lichii/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/feature-arm64-build-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
fail() { echo "FAIL: $*" >&2; exit 1; }
trap 'rc=$?; if ((rc != 0)); then echo "FAIL: exit code $rc"; echo "Full log: $LOG"; fi' EXIT
echo "===== LICHII ARM64 HARDWARE + CONTROLLER FEATURE BUILD ====="
echo "Log: $LOG"
[[ "$(uname -m)" == aarch64 ]] || fail "This build requires the Odin ARM64."
[[ -d "$SOURCE/.git" ]] || fail "Original source checkout missing."
[[ -x "$STABLE" && -x "$OLD_PREVIEW" ]] || fail "Stable or original preview executable missing."
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || fail "Build parallelism must be a positive integer."
command -v toolbox >/dev/null || fail "toolbox missing."
command -v git >/dev/null || fail "git missing."
command -v python3 >/dev/null || fail "python3 missing."
[[ ! -L "$LOGDIR" ]] || fail "Log directory is a symlink."
ORIGINAL_HEAD="$(git -C "$SOURCE" rev-parse HEAD)"
STABLE_HASH="$(sha256sum "$STABLE" | awk '{print $1}')"
OLD_HASH="$(sha256sum "$OLD_PREVIEW" | awk '{print $1}')"
echo "Original HEAD: $ORIGINAL_HEAD"
echo "===== FETCH FEATURE WITHOUT SWITCHING ORIGINAL BRANCH ====="
git -C "$SOURCE" fetch --no-tags origin "refs/heads/$BRANCH"
SHA="$(git -C "$SOURCE" rev-parse FETCH_HEAD)"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || fail "Could not verify feature commit."
SHORT="${SHA:0:12}"
WT="$ROOT/worktrees/hardware-controller-$SHORT"
BUILD="$ROOT/build-hardware-controller-$SHORT"
[[ ! -L "$WT" && ! -L "$BUILD" ]] || fail "Refusing unexpected symlink."
echo "Feature commit: $SHA"
echo "Separate worktree: $WT"
echo "Separate build: $BUILD"
if [[ -e "$WT" ]]; then
    [[ -f "$WT/.git" || -d "$WT/.git" ]] || fail "Existing worktree path not a Git checkout."
    [[ "$(git -C "$WT" rev-parse HEAD)" == "$SHA" ]] || fail "Worktree has a different revision."
    [[ -z "$(git -C "$WT" status --porcelain --untracked-files=no)" ]] ||
        fail "Worktree has local edits; not overwriting."
    echo "Reusing correct revision worktree."
else
    mkdir -p "$ROOT/worktrees"
    git -C "$SOURCE" worktree add --detach "$WT" "$SHA"
fi
git -C "$WT" submodule update --init --recursive
echo "===== PYTHON UNIT TESTS (ISOLATED HOME AND FEATURE SOURCE) ====="
TESTS_HOME="$ROOT/test-runs/unit-tests-$SHORT"
mkdir -p "$TESTS_HOME/Applications/Lichii"
if [[ ! -e "$TESTS_HOME/Applications/Lichii/source" ]]; then
    ln -s "$WT" "$TESTS_HOME/Applications/Lichii/source"
fi
[[ "$(readlink -f "$TESTS_HOME/Applications/Lichii/source")" == "$(readlink -f "$WT")" ]] ||
    fail "Tests home already points to another source. Refusing."
(cd "$WT" && HOME="$TESTS_HOME" python3 -m unittest discover -s scripts/tests -p 'test_*.py' -v)
echo "===== CMAKE CONFIGURATION ====="
toolbox run --container "$BOX" cmake -S "$WT" -B "$BUILD" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DYUZU_TESTS=OFF \
    -DVulkanHeaders_FORCE_BUNDLED=ON -DCMAKE_CXX_FLAGS=-Wno-error=shadow
echo "===== ARM64 COMPILATION ====="
toolbox run --container "$BOX" cmake --build "$BUILD" --target yuzu --parallel "$JOBS"
BIN="$BUILD/bin/lichii"
[[ -x "$BIN" ]] || fail "No ARM64 candidate built."
if command -v readelf >/dev/null; then
    readelf -h "$BIN" | grep -q 'Machine:.*AArch64' || fail "Candidate is not AArch64."
fi
[[ "$(sha256sum "$STABLE" | awk '{print $1}')" == "$STABLE_HASH" ]] ||
    fail "Stable executable hash changed."
[[ "$(sha256sum "$OLD_PREVIEW" | awk '{print $1}')" == "$OLD_HASH" ]] ||
    fail "Original Steam Menu preview hash changed."
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "$ORIGINAL_HEAD" ]] ||
    fail "Original source revision changed."
echo "PASS: Feature ARM64 build succeeded. Original source and binaries unchanged."
echo "===== PREPARE ISOLATED RUNTIME CONFIG ====="
SESSION="$ROOT/test-runs/hardware-controller-$SHORT-$(date +%Y%m%d-%H%M%S)"
TESTHOME="$SESSION/home"
FRESH="$SESSION/config-fresh"
COPIED="$SESSION/config-copied"
CACHE="$SESSION/cache"
mkdir -p "$TESTHOME/Applications/Lichii" "$FRESH" "$COPIED/lichii" "$CACHE"
ln -s "$SOURCE" "$TESTHOME/Applications/Lichii/source"
if [[ -f "$CONFIG_HOME/lichii/qt-config.ini" ]]; then
    cp -p "$CONFIG_HOME/lichii/qt-config.ini" "$COPIED/lichii/qt-config.ini"
    echo "Original qt-config.ini COPIED into the isolated test config."
fi
mkdir -p "$REAL_HOME/.local/bin" "$REAL_HOME/.local/share/applications"
GAME_LAUNCH="$REAL_HOME/.local/bin/lichii-hardware-controller-preview"
FRESH_LAUNCH="$REAL_HOME/.local/bin/lichii-hardware-first-run-preview"
make_launcher() {
    local dest="$1" cfg="$2" binaryq boxq homeq cfgq cacheq dataq sessionq
    printf -v binaryq '%q' "$BIN"
    printf -v boxq '%q' "$BOX"
    printf -v homeq '%q' "$TESTHOME"
    printf -v cfgq '%q' "$cfg"
    printf -v cacheq '%q' "$CACHE"
    printf -v dataq '%q' "$DATA_HOME"
    printf -v sessionq '%q' "$SESSION"
    cat > "$dest" <<LAUNCH
#!/usr/bin/env bash
set -Eeuo pipefail
cd $sessionq
exec toolbox run --container $boxq env HOME=$homeq XDG_CONFIG_HOME=$cfgq XDG_CACHE_HOME=$cacheq XDG_DATA_HOME=$dataq QT_QPA_PLATFORM=wayland VK_DRIVER_FILES=/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json $binaryq "\$@"
LAUNCH
    chmod +x "$dest"
    bash -n "$dest" || fail "Generated test launcher failed syntax check."
}
make_launcher "$GAME_LAUNCH" "$COPIED"
make_launcher "$FRESH_LAUNCH" "$FRESH"
cat > "$REAL_HOME/.local/share/applications/lichii-hardware-controller-preview.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=Lichii (Hardware + Controller Preview)
Comment=Isolated Lichii ARM64 diagnostics and controller routing
Exec=$GAME_LAUNCH
Icon=applications-games
Terminal=false
Categories=Game;Emulator;
StartupNotify=true
DESKTOP
if command -v kbuildsycoca6 >/dev/null; then kbuildsycoca6 >/dev/null 2>&1 || true; fi
echo "PASS: Safe launchers installed:"
echo "  With COPY of current settings: $GAME_LAUNCH"
echo "  With FRESH default settings:  $FRESH_LAUNCH"
echo "  Test home: $TESTHOME"
echo "  Existing Lichii settings and executables are untouched."
echo "  Game saves may still update during normal gameplay (shared XDG_DATA_HOME)."
echo "===== OPEN TEST PREVIEW ====="
echo "In the preview: Help > Hardware & Controller Diagnostics."
echo "Check controllers; test the new Steam submenus without importing/clearing anything."
echo "Close the window to print the final report."
set +e
"$GAME_LAUNCH"
RC=$?
set -e
echo "Candidate application exit code: $RC"
echo "===== HARDWARE REPORT ====="
REPORT="$TESTHOME/.local/share/lichii/logs/hardware-detection-latest.json"
if [[ -f "$REPORT" ]]; then
    python3 - "$REPORT" <<'PYTHON'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f: d = json.load(f)
print("Report:", sys.argv[1])
print("CPU:", d.get("cpu"))
print("GPU:", [x.get("name") for x in d.get("gpus", [])])
print("Handheld:", d.get("handheld_profile"))
a=d.get("controller_assignment", {})
print("ArmadaOS mode:", a.get("armada_controller_mode"))
print("Prefer external:", a.get("prefer_external_player_1"))
print("Controllers:", [(x.get("name"), x.get("is_built_in"), x.get("transport")) for x in a.get("devices", [])])
print("Controller diagnostic note:", a.get("note", ""))
PYTHON
else
    echo "WARNING: No automatic hardware report found; check runtime log."
fi
[[ "$(sha256sum "$STABLE" | awk '{print $1}')" == "$STABLE_HASH" ]] ||
    fail "Stable executable changed after testing."
[[ "$(sha256sum "$OLD_PREVIEW" | awk '{print $1}')" == "$OLD_HASH" ]] ||
    fail "Original preview executable changed after testing."
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "$ORIGINAL_HEAD" ]] ||
    fail "Original source revision changed."
echo "PASS: Stable executable and previous preview hashes unchanged."
echo "PASS: Original source HEAD unchanged."
echo "Full build log: $LOG"
echo "First-run test launcher: $FRESH_LAUNCH"
echo "Compiled candidate: $BIN"
if ((RC != 0)); then fail "The candidate exited unsuccessfully ($RC)."; fi
echo "PASS: Build + startup smoke test completed."
echo "Hands-on controller mappings and game performance still need verification."

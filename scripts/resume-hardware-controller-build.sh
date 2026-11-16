#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Incremental build of the isolated hardware/controller feature branch.
# Reuses the known working test worktree and build; never changes stable Lichii.
set -Eeuo pipefail
SRC="$HOME/Applications/Lichii/source"
ROOT="$HOME/Applications/Lichii"
WT="$ROOT/worktrees/hardware-controller-1257f2396da8"
BUILD="$ROOT/build-hardware-controller-1257f2396da8"
STABLE="$ROOT/bin/lichii-odin"
OLD="$ROOT/build-steam-menu-test/bin/lichii"
BRANCH="feature/startup-hardware-diagnostics-20261112"
BOX="${LICHII_TOOLBOX:-lichii-debug}"
LOGDIR="$HOME/.local/share/lichii/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/hardware-controller-resume-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
fail() { echo "FAIL: $*" >&2; exit 1; }
trap 'rc=$?; if ((rc != 0)); then echo "Stopped with exit $rc"; echo "Log: $LOG"; fi' EXIT
echo "===== Lichii ARM64 incremental resume ====="
echo "Log: $LOG"
[[ "$(uname -m)" == "aarch64" ]] || fail "Must run on the Odin ARM64."
[[ -d "$SRC/.git" && -e "$WT/.git" ]] || fail "Original Git source or failed-build worktree missing."
[[ -f "$BUILD/build.ninja" ]] || fail "Original build.ninja missing; cannot safely reuse the existing build."
[[ -x "$STABLE" && -x "$OLD" ]] || fail "Stable/old preview executable missing."
[[ ! -L "$WT" && ! -L "$BUILD" ]] || fail "Unsafe symlink at build/worktree."
[[ -z "$(git -C "$WT" status --porcelain --untracked-files=no)" ]] ||
    fail "Feature worktree has tracked local changes; aborting without overwriting."
# Only accept a descendant of the known first feature build, and ensure the
# existing worktree revision is an ancestor of the fetched candidate.
FIRST_SHA="1257f2396da8a57beaafc680bae5f4539b60a478"
git -C "$WT" merge-base --is-ancestor "$FIRST_SHA" HEAD ||
    fail "Existing worktree is unrelated to the known isolated feature build."
command -v toolbox >/dev/null || fail "toolbox unavailable."
STABLE_HASH="$(sha256sum "$STABLE" | awk '{print $1}')"
OLD_HASH="$(sha256sum "$OLD" | awk '{print $1}')"
ORIGINAL_HEAD="$(git -C "$SRC" rev-parse HEAD)"
echo "===== Fetching current isolated feature branch ====="
git -C "$SRC" fetch --no-tags origin "refs/heads/$BRANCH"
FIXED_SHA="$(git -C "$SRC" rev-parse FETCH_HEAD)"
echo "Feature commit: $FIXED_SHA"
git -C "$WT" merge-base --is-ancestor HEAD "$FIXED_SHA" ||
    fail "Current test worktree is not an ancestor of the latest feature branch."
git -C "$WT" checkout --detach "$FIXED_SHA"
[[ "$(git -C "$WT" rev-parse HEAD)" == "$FIXED_SHA" ]] ||
    fail "Feature worktree checkout did not reach expected commit."
echo "===== Verify Controls preference placement (read-only tests) ====="
(cd "$WT" && python3 -m unittest discover -s scripts/tests -p 'test_controls_priority_ui.py' -v)
(cd "$WT" && python3 -m unittest discover -s scripts/tests -p 'test_builtin_exclusive_player1.py' -v)
(cd "$WT" && python3 -m unittest discover -s scripts/tests -p 'test_idle_controller_hotplug.py' -v)
echo "===== CMake refresh, preserving existing compiled objects ====="
toolbox run --container "$BOX" cmake -S "$WT" -B "$BUILD" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DYUZU_TESTS=OFF \
    -DVulkanHeaders_FORCE_BUNDLED=ON -DCMAKE_CXX_FLAGS=-Wno-error=shadow
SDL_LIST="$WT/.cache/cpm/sdl3/release-3.4.8/src/joystick/controller_list.h"
[[ -f "$SDL_LIST" ]] || fail "Bundled SDL3 controller registry unavailable."
if ! grep -Fq 'MAKE_CONTROLLER_ID( 0x28de, 0x12f0 )' "$SDL_LIST"; then
    fail "InputPlumber Deck UHID SDL3 compatibility alias was not applied. Build cancelled."
fi
echo "PASS: Bundled SDL3 includes ArmadaOS 28DE:12F0 compatibility."
SDL_HIDAPI="$WT/.cache/cpm/sdl3/release-3.4.8/src/joystick/hidapi/SDL_hidapijoystick.c"
IDLE_PATCH="$WT/.patch/sdl3/armada-toolbox-idle-hidapi-reprobe.patch"
[[ -f "$SDL_HIDAPI" && -f "$IDLE_PATCH" ]] ||
    fail "Bundled SDL3 hotplug source/patch unavailable."
if ! grep -Fq 'LICHII_IDLE_HIDAPI_REFRESH' "$SDL_HIDAPI"; then
    echo "Applying isolated SDL3 idle-only HIDAPI hotplug fallback."
    command -v patch >/dev/null || fail "patch command is required on Odin host."
    patch --batch --forward -d "$WT/.cache/cpm/sdl3/release-3.4.8" -p1 < "$IDLE_PATCH" ||
        fail "SDL3 idle-hotplug patch failed. Stable executable remains untouched."
fi
grep -Fq 'LICHII_IDLE_HIDAPI_REFRESH' "$SDL_HIDAPI" ||
    fail "SDL3 hotplug fallback is missing; build cancelled."
echo "PASS: SDL3 idle-only HID rescan fallback installed."
echo "===== Incremental ARM64 compile ====="
toolbox run --container "$BOX" cmake --build "$BUILD" --target yuzu --parallel 4
BIN="$BUILD/bin/lichii"
[[ -x "$BIN" ]] || fail "No candidate executable found."
if command -v readelf >/dev/null 2>&1; then
    readelf -h "$BIN" | grep -q 'Machine:.*AArch64' ||
        fail "Built executable is not AArch64."
fi
[[ "$(sha256sum "$STABLE" | awk '{print $1}')" == "$STABLE_HASH" ]] ||
    fail "Stable Lichii executable unexpectedly changed."
[[ "$(sha256sum "$OLD" | awk '{print $1}')" == "$OLD_HASH" ]] ||
    fail "Old Steam Menu Test executable unexpectedly changed."
[[ "$(git -C "$SRC" rev-parse HEAD)" == "$ORIGINAL_HEAD" ]] ||
    fail "Original source HEAD unexpectedly changed."
echo "PASS: ARM64 feature candidate built. Stable executable and original source untouched."

echo "===== Isolated preview session ====="
NOW="$(date +%Y%m%d-%H%M%S)"
SESSION="$ROOT/test-runs/hardware-controller-fixed-$NOW"
TESTHOME="$SESSION/home"
CFG="$SESSION/config"
CACHE="$SESSION/cache"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
REALCFG="${XDG_CONFIG_HOME:-$HOME/.config}"
mkdir -p "$TESTHOME/Applications/Lichii" "$CFG/lichii" "$CACHE"
ln -s "$SRC" "$TESTHOME/Applications/Lichii/source"
# Keep opted-in automatic routing and its matching saved P1/P2 config across
# isolated test launches. Copy from the prior isolated session only, never
# edit the stable HOME/config or any working binary.
PREVIOUS_RUN=""
if [[ -d "$ROOT/test-runs" ]]; then
    PREVIOUS_NAME="$(find "$ROOT/test-runs" -mindepth 1 -maxdepth 1 -type d \
        -name 'hardware-controller-fixed-*' ! -name "hardware-controller-fixed-$NOW" \
        -printf '%f\n' | sort | tail -n 1)"
    if [[ -n "$PREVIOUS_NAME" ]]; then
        PREVIOUS_RUN="$ROOT/test-runs/$PREVIOUS_NAME"
    fi
fi
if [[ -n "$PREVIOUS_RUN" && ! -L "$PREVIOUS_RUN" &&
      -f "$PREVIOUS_RUN/config/lichii/qt-config.ini" &&
      -f "$PREVIOUS_RUN/home/.config/lichii/controller-routing.ini" &&
      ! -L "$PREVIOUS_RUN/config/lichii/qt-config.ini" &&
      ! -L "$PREVIOUS_RUN/home/.config/lichii/controller-routing.ini" ]]; then
    cp -p "$PREVIOUS_RUN/config/lichii/qt-config.ini" "$CFG/lichii/qt-config.ini"
    mkdir -p "$TESTHOME/.config/lichii"
    cp -p "$PREVIOUS_RUN/home/.config/lichii/controller-routing.ini" \
        "$TESTHOME/.config/lichii/controller-routing.ini"
    echo "Restored previous ISOLATED preview config and controller-routing consent."
elif [[ -f "$REALCFG/lichii/qt-config.ini" ]]; then
    cp -p "$REALCFG/lichii/qt-config.ini" "$CFG/lichii/qt-config.ini"
    echo "Copied original Qt config into isolated test; automatic mapping may require explicit opt-in."
fi
echo "Launch with separate HOME and configuration."
echo "Check Controls: bottom-left external-P1 checkbox ABOVE Console Mode (Docked/Handheld)."
echo "Check the external P1 checkbox is enabled above Console Mode."
echo "With one external and checkbox ON: external P1; built-in unassigned."
echo "With one external and checkbox OFF: built-in Odin P1; external P2 (TV multiplayer)."
echo "With two externals and checkbox ON: first external P1; second external P2."
echo "Check the built-in controller never becomes Player 2."
echo "Switch checkbox ON/OFF once in Controls; pressing OK opts in to idle automatic mapping."
echo "Then, while NO GAME is running, plug/unplug the USB controller: P1/P2 should update without Apply."
echo "Help > Hardware & Controller Diagnostics shows Last routing check, Automatic mapping, and USB Steam Controller HID status."
echo "If USB Steam HID is PRESENT but absent from SDL, no false P1/P2 reassignment will occur."
echo "Diagnostics show actual P1/P2 mappings, SDL HIDAPI enumeration, and why a controller cannot be assigned."
echo "In Controls, automatically routed P1/P2 should display their real mapped device instead of Any."
echo "Manual gamepad edits still pause automation; re-enable explicitly in Diagnostics if needed."
echo "Check Help > Hardware & Controller Diagnostics: Steam Deck 0 recognized as BUILT-IN."
echo "Try buttons and both analog sticks inside Controls; verify Steam menu structure."
echo "Do not reset or perform Steam import/scrape/clear operations during initial check."
echo "Close Lichii normally to see the test results."
set +e
(
    cd "$SESSION"
    toolbox run --container "$BOX" env \
        HOME="$TESTHOME" XDG_CONFIG_HOME="$CFG" XDG_CACHE_HOME="$CACHE" \
        XDG_DATA_HOME="$DATA" QT_QPA_PLATFORM=wayland \
        SDL_JOYSTICK_HIDAPI=1 SDL_JOYSTICK_HIDAPI_STEAM=1 \
        SDL_JOYSTICK_HIDAPI_STEAMDECK=1 \
        VK_DRIVER_FILES=/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json \
        "$BIN"
)
RC=$?
set -e
echo "Preview exited with status: $RC"
REPORT="$TESTHOME/.local/share/lichii/logs/hardware-detection-latest.json"
if [[ -f "$REPORT" ]]; then
    python3 - "$REPORT" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as f: x = json.load(f)
print('--- Detected hardware ---')
print('CPU:', x.get('cpu'))
print('GPUs:', [g.get('name') for g in x.get('gpus', [])])
print('Handheld profile:', x.get('handheld_profile'))
c = x.get('controller_assignment', {})
print('ArmadaOS controller mode:', c.get('armada_controller_mode'))
print('Controllers:', [(d.get('name'), d.get('is_built_in'), d.get('transport'))
                       for d in c.get('devices', [])])
print('Identity note:', c.get('note', ''))
PY
else
    echo "WARNING: No automatic hardware JSON report created."
fi
[[ "$(sha256sum "$STABLE" | awk '{print $1}')" == "$STABLE_HASH" ]] ||
    fail "Stable executable checksum changed."
[[ "$(sha256sum "$OLD" | awk '{print $1}')" == "$OLD_HASH" ]] ||
    fail "Original preview checksum changed."
echo "PASS: Original working executables unchanged."
echo "Full log: $LOG"
if ((RC != 0)); then fail "New preview exited with code $RC."; fi
echo "PASS: Incremental compile and startup smoke test completed."
echo "Controller/gameplay tests remain to be verified."

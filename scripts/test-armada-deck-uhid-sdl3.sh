#!/usr/bin/env bash
# Preview-only SDL3 test for InputPlumber's Valve 28DE:12F0 deck-uhid target.
# Not for stable Lichii. Does not modify controller modes, udev or system settings.
set -Eeuo pipefail
ROOT="$HOME/Applications/Lichii"
SOURCE="$ROOT/source"
WT="$ROOT/worktrees/hardware-controller-1257f2396da8"
BUILD="$ROOT/build-hardware-controller-1257f2396da8"
BOX="${LICHII_TOOLBOX:-lichii-debug}"
STABLE="$ROOT/bin/lichii-odin"
OLD="$ROOT/build-steam-menu-test/bin/lichii"
SDL_LIST="$WT/.cache/cpm/sdl3/release-3.4.8/src/joystick/controller_list.h"
BRANCH="feature/startup-hardware-diagnostics-20261112"
LOGDIR="$HOME/.local/share/lichii/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/test-armada-sdl12f0-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
fail() { echo "FAIL: $*" >&2; exit 1; }
trap 'rc=$?; if ((rc != 0)); then echo "Test stopped with exit code $rc; log: $LOG"; fi' EXIT

echo "=== ARMADA deck-uhid / SDL3 COMPATIBILITY EXPERIMENT ==="
echo "Log: $LOG"
[[ "$(uname -m)" == "aarch64" ]] || fail "This test requires an ARM64 Odin."
[[ -d "$SOURCE/.git" && -e "$WT/.git" && -f "$BUILD/build.ninja" ]] ||
    fail "Expected separate feature worktree/build not found."
[[ -x "$STABLE" && -x "$OLD" ]] || fail "Working stable or old preview executable missing."
[[ ! -L "$WT" && ! -L "$BUILD" && ! -L "$SDL_LIST" ]] ||
    fail "An unexpected build path is a symbolic link."
[[ -f "$SDL_LIST" ]] || fail "Bundled SDL 3.4.8 controller registry missing."
[[ -z "$(git -C "$WT" status --porcelain --untracked-files=no)" ]] ||
    fail "Feature worktree contains tracked edits; refusing to overwrite."
[[ "$(cat /etc/armada/controller.conf 2>/dev/null)" == "controller_type=deck-uhid" ]] ||
    fail "The host is no longer using deck-uhid; experiment not applicable."
[[ -d /sys/devices/virtual/misc/uhid ]] ||
    fail "No UHID source found at the known ArmadaOS sysfs location."
[[ -e /dev/hidraw0 ]] || fail "No /dev/hidraw0 node."
if ! readlink -f /sys/class/hidraw/hidraw0/device | grep -qi '28DE:12F0'; then
    fail "hidraw0 is no longer the InputPlumber 28DE:12F0 target."
fi
command -v toolbox >/dev/null || fail "toolbox missing."
command -v python3 >/dev/null || fail "python3 missing."
BASE_HEAD="$(git -C "$SOURCE" rev-parse HEAD)"
STABLE_SHA="$(sha256sum "$STABLE" | awk '{print $1}')"
OLD_SHA="$(sha256sum "$OLD" | awk '{print $1}')"

echo "=== Update isolated source checkout ==="
git -C "$SOURCE" fetch --no-tags origin "refs/heads/$BRANCH"
REV="$(git -C "$SOURCE" rev-parse FETCH_HEAD)"
git -C "$WT" merge-base --is-ancestor HEAD "$REV" ||
    fail "Feature source diverged; refusing automatic checkout."
git -C "$WT" checkout --detach "$REV"
echo "Feature revision: $REV"

echo "=== Add one provisional SDL driver alias (feature worktree ONLY) ==="
python3 - "$SDL_LIST" <<'PYTHON'
from pathlib import Path
import sys
path = Path(sys.argv[1])
s = path.read_text(encoding="utf-8")
anchor = "{ MAKE_CONTROLLER_ID( 0x28de, 0x1205 ), k_eControllerType_SteamControllerNeptune, NULL }"
alias = "{ MAKE_CONTROLLER_ID( 0x28de, 0x12f0 ), k_eControllerType_SteamControllerNeptune, NULL }"
if alias in s:
    print("SDL alias already present, no changes made.")
else:
    if s.count(anchor) != 1:
        raise SystemExit("FAIL: Unexpected upstream SDL3 controller table; did not patch.")
    line = next(l for l in s.splitlines(keepends=True) if anchor in l)
    additional = line[:len(line)-len(line.lstrip())] + alias + ", // EXPERIMENT: InputPlumber deck-uhid; do not promote without testing\n"
    path.write_text(s.replace(line,line+additional,1),encoding="utf-8")
    print("Added experimental 28DE:12F0 alias to isolated bundled SDL3 registry.")
assert alias in path.read_text(encoding="utf-8")
PYTHON

echo "=== Incremental compile: SDL3 + Lichii ==="
toolbox run --container "$BOX" cmake --build "$BUILD" --target yuzu --parallel 4
BIN="$BUILD/bin/lichii"
[[ -x "$BIN" ]] || fail "No built preview binary after SDL test."
[[ "$(sha256sum "$STABLE" | awk '{print $1}')" == "$STABLE_SHA" ]] ||
    fail "Stable binary modified."
[[ "$(sha256sum "$OLD" | awk '{print $1}')" == "$OLD_SHA" ]] ||
    fail "Old preview binary modified."
echo "PASS: Experimental candidate compiled. Working executables unchanged."

echo "=== Launch separate session with original game directories read-only settings copy ==="
SESSION="$ROOT/test-runs/sdl-deck-uhid-$(date +%Y%m%d-%H%M%S)"
THOME="$SESSION/home"
TCFG="$SESSION/config"
TCACHE="$SESSION/cache"
mkdir -p "$THOME/Applications/Lichii" "$TCFG/lichii" "$TCACHE"
ln -s "$SOURCE" "$THOME/Applications/Lichii/source"
CONFIG_SRC="${XDG_CONFIG_HOME:-$HOME/.config}/lichii/qt-config.ini"
if [[ -f "$CONFIG_SRC" ]]; then cp -p "$CONFIG_SRC" "$TCFG/lichii/qt-config.ini"; fi
echo "Check Help > Hardware & Controller Diagnostics: does SDL show the built-in controller?"
echo "If detected, open Controls to confirm buttons/sticks respond."
echo "Do not change controller emulation mode or permissions during this test."
echo "Exit Lichii normally to print diagnostic results."
set +e
(
    cd "$SESSION"
    toolbox run --container "$BOX" env \
        HOME="$THOME" XDG_CONFIG_HOME="$TCFG" XDG_CACHE_HOME="$TCACHE" \
        XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}" \
        QT_QPA_PLATFORM=wayland \
        SDL_JOYSTICK_HIDAPI=1 SDL_JOYSTICK_HIDAPI_STEAMDECK=1 \
        VK_DRIVER_FILES=/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json \
        "$BIN"
)
RC=$?
set -e
echo "Lichii return code: $RC"

REPORT="$THOME/.local/share/lichii/logs/hardware-detection-latest.json"
if [[ -f "$REPORT" ]]; then
    python3 - "$REPORT" <<'PYTHON'
import json,sys
with open(sys.argv[1],encoding='utf8') as f: d=json.load(f)
print("Controller backend devices:",d.get('controllers_usable_by_lichii'))
c=d.get('controller_assignment',{})
print("ArmadaOS mode:",c.get('armada_controller_mode'))
print("Controller identities:",[(x.get('name'),x.get('is_built_in'),x.get('transport')) for x in c.get('devices',[])])
print("Controller note:",c.get('note'))
PYTHON
else
    echo "WARNING: No startup hardware report saved."
fi
[[ "$(sha256sum "$STABLE" | awk '{print $1}')" == "$STABLE_SHA" ]] ||
    fail "Stable Lichii executable unexpectedly changed."
[[ "$(sha256sum "$OLD" | awk '{print $1}')" == "$OLD_SHA" ]] ||
    fail "Old Steam Menu Test executable unexpectedly changed."
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "$BASE_HEAD" ]] ||
    fail "Original source checkout moved."
echo "PASS: Original stable and Steam Menu executables remain untouched."
echo "Log: $LOG"
echo "WARNING: The SDL alias is EXPERIMENTAL; success requires usable SDL buttons/axes."
if ((RC != 0)); then fail "Preview application returned $RC."; fi
echo "PASS: Experimental Lichii launch completed; review detected controllers above."

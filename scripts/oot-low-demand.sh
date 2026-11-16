#!/usr/bin/env bash
# Experimental Odin 3 / ArmadaOS low-demand Ocarina profile.
# Run in the same Fedora ARM64 toolbox as Lichii. Does not edit any game files,
# shared configuration, saved games, graphics drivers, artwork or other installs.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: oot-low-demand.sh [--profile] [--aggressive] [-- Lichii arguments...]

  (no options)   Start experimental Lichii with reversible OOT-only low-demand mode.
  --profile      Also record GPU timestamps and capture the exact slow compute SPIR-V.
  --hmma-lds     Opt-in software tensor/HMMA shared-memory substitution for the
                 exact captured Ocarina shader. A/B test; NOT yet gameplay-validated.
  --aggressive   Optional UNSAFE-for-rendering A/B: skip one identified unused network
                 compute pass only after the No sharpening output bypass succeeds.
                 May cause visual errors; not proven on Odin.

For a standalone source script, set LICHII_EXPERIMENT_BIN to the path of the
experimental binary. A script packaged next to the binary detects it itself.
You must select Ocarina of Time (0400486024DEC000) inside Lichii.
Use system Mesa Turnip; never runs krfb-virtualmonitor or changes host packages.
HELP
}

profile=0
aggressive=0
hmma_lds=0
while (( $# )); do
    case "$1" in
        --profile) profile=1; shift ;;
        --hmma-lds) hmma_lds=1; shift ;;
        --aggressive) aggressive=1; shift ;;
        --help|-h) usage; exit 0 ;;
        --) shift; break ;;
        -*) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
        *) break ;;
    esac
done

if [[ "$(uname -m)" != "aarch64" ]]; then
    echo "STOP: This test is for AArch64/ArmadaOS, not this host." >&2
    exit 1
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
binary="${LICHII_EXPERIMENT_BIN:-}"
if [[ -z "$binary" ]]; then
    for candidate in "$script_dir/lichii" "$script_dir/../usr/bin/lichii" \
                     "$script_dir/../bin/lichii"; do
        if [[ -x "$candidate" && ! -d "$candidate" ]]; then
            binary="$candidate"
            break
        fi
    done
fi
if [[ -z "$binary" || ! -x "$binary" ]]; then
    echo "STOP: experimental Lichii binary not found; nothing changed." >&2
    echo "Set LICHII_EXPERIMENT_BIN or run the script inside the extracted test package." >&2
    exit 1
fi

icd=/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json
if [[ ! -f "$icd" ]]; then
    echo "STOP: Fedora/ArmadaOS system Turnip driver ICD is absent: $icd" >&2
    exit 1
fi

# These are runtime process variables; nothing is written to ~/.config or the game.
# Avoid reusing the stable game's compiled shader cache for a different HMMA
# translation. XDG_CACHE_HOME controls EdenPath::ShaderDir on Linux; no cache
# folders are deleted and the normal game's cache stays untouched.
if (( hmma_lds )); then
    export XDG_CACHE_HOME="$HOME/.cache/lichii-oot-extra-compute-trace-v2"
    mkdir -p -- "$XDG_CACHE_HOME"
    original="$HOME/.local/share/lichii/dump/0400486024dec000_03bf0ffc7d2d0bed.spv"
    saved="$HOME/Development/turnip-a830-drm/oot-hmma-lds-original/0400486024dec000_03bf0ffc7d2d0bed.spv"
    if [[ -s "$original" && ! -e "$saved" ]]; then
        mkdir -p -- "$(dirname -- "$saved")"
        cp -n -- "$original" "$saved"
        echo "Preserved pre-LDS diagnostic SPIR-V at: $saved"
    fi
fi
export EDEN_NX2_OOT_LOW_DEMAND=1
export EDEN_NX2_OOT_HMMA_LDS="$hmma_lds"
export EDEN_NX2_OOT_SKIP_UNUSED_HEAVY="$aggressive"
export VK_DRIVER_FILES="$icd"
export QT_QPA_PLATFORM=wayland
if (( profile )); then
    export EDEN_NX2_OOT_SLOW_COMPUTE_TRACE=1
    export EDEN_NX2_GPU_PROFILE=1
    export EDEN_DKB_FRAME_TRACE=1
else
    # Nx2Profile checks whether the env var exists, not whether it equals "1".
    # Setting EDEN_NX2_GPU_PROFILE=0 would still enable it and spoil FPS comparisons.
    unset EDEN_NX2_OOT_SLOW_COMPUTE_TRACE
    unset EDEN_NX2_GPU_PROFILE
    unset EDEN_DKB_FRAME_TRACE
fi

echo "=== OOT ARM64 LOW-DEMAND EXPERIMENT ==="
echo "Binary: $binary"
echo "Driver: system Mesa Turnip"
echo "Profile: low-demand (only title 0400486024DEC000)"
echo "GPU trace: $profile; HMMA LDS: $hmma_lds; older optional heavy-network bypass: $aggressive"
echo "Existing settings, save data and other games: unchanged"
echo "Suggested per-game settings: Handheld mode, Vulkan, 1X scaling, NCE."
echo "Select Ocarina inside the GUI and close Lichii normally at the end."

set +e
env -u VK_ICD_FILENAMES -u VK_ADD_DRIVER_FILES \
    -u EDEN_NX2_NO_MESH -u EDEN_NX2_NO_MESH_FILE \
    "$binary" "$@"
status=$?
set -e

if (( profile )); then
    log="$HOME/.local/share/lichii/log/eden_log.txt"
    out="$HOME/Development/turnip-a830-drm/oot-low-demand-profiles/$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$out"
    if [[ -f "$log" ]]; then
        cp -p -- "$log" "$out/eden-oot-low-demand.txt"
        echo
        echo "=== GPU PROFILE: SLOW COMPUTE ==="
        grep -E 'NX2 OOT compute trace|OOT HMMA LDS enabled|DKB gpu_frame|DKB gpu_work|Async read-back per second' \
            "$log" | tail -n 25 || true
        echo "Full log: $out/eden-oot-low-demand.txt"
        echo "Captured SPIR-V files (only the 3 measured compute hashes):"
        find "$HOME/.local/share/lichii/dump" -maxdepth 3 -type f \
             \( -name '*_03bf0ffc7d2d0bed.spv' -o -name '*_e40f5efb5480e692.spv' \
                -o -name '*_9302bc0d6d1d9bc1.spv' \) -print 2>/dev/null || true
        if (( hmma_lds )); then
            python3 - "$log" <<'PY'
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from datetime import datetime
import sys
home = Path.home()
log = Path(sys.argv[1])
dump_dir = home / ".local/share/lichii/dump"
hashes = ("03bf0ffc7d2d0bed", "e40f5efb5480e692", "9302bc0d6d1d9bc1")
output = home / "Downloads" / ("oot-extra-compute-trace-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".zip")
captured = []
with ZipFile(output, "w", ZIP_DEFLATED) as archive:
    archive.write(log, "eden-oot-extra-compute.log")
    for hash_value in hashes:
        candidates = list(dump_dir.rglob("*_" + hash_value + ".spv")) if dump_dir.exists() else []
        if candidates:
            shader = max(candidates, key=lambda f: f.stat().st_mtime)
            archive.write(shader, shader.name)
            captured.append(hash_value)
    archive.writestr("capture-status.txt",
                     "Captured: " + ", ".join(captured) + "\\n" +
                     "Missing: " + ", ".join(h for h in hashes if h not in captured) + "\\n")
print("=== OOT EXTRA-COMPUTE DIAGNOSTIC ZIP ===")
print(output)
print("Captured hashes:", ", ".join(captured) if captured else "none")
print("Attach this ZIP to ChatGPT for further shader analysis.")
PY
        fi
    else
        echo "No internal Eden log found; profiling capture unavailable."
    fi
fi
exit "$status"

# Lichii — Odin 3 / Odin 2 ARM64 on ArmadaOS

> **Status: Odin 3 Ultra field-tested; Odin 2 experimental / not yet verified.**
> This is an install-and-maintenance *supplement* to upstream [Lichii](https://github.com/zortos293/Lichii), not a standalone emulator. The verified ARM64 modifications are published in the **`odin-armadaos` branch** of this fork. Clone that branch, not upstream `nx2`, to obtain the patches.

## What this fork addresses

The initial ARM64 native-code execution (NCE) release crashed on `MRS CNTPCT_EL0`. The locally-tested branch adds timer handling for runtime NRO code, fixes the two-pass NSO loader so RomFS/ExeFS patches are visible to the first NCE scanning pass, and includes necessary GCC 16 build compatibility fixes. With the correct driver, the Odin 3 Ultra has launched Ocarina of Time at an observed 60 FPS. This is a single-device, single-game observation, not a performance guarantee.

Runtime configuration matters just as much as source changes:

* **Qt** must run through native Wayland (`QT_QPA_PLATFORM=wayland`) to avoid frontend/menu stutters seen on this device.
* **Vulkan** must use the Turnip driver (`VK_DRIVER_FILES=/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json`). Without this the toolbox picked `llvmpipe`, a CPU software renderer, at 6–16 FPS.
* **InputPlumber** should expose an Xbox Elite pad (`xbox-elite`) if SDL3 sees zero controllers while the physical AYN gamepad is claimed by InputPlumber.
* In Lichii configure NCE, Vulkan, Handheld mode, Pro Controller for Player 1, **No Sharpening**, 0.5x resolution, and GPU accuracy Low (the last may be a hidden option but verified via log).

## Verified machine

* AYN Odin 3 **Ultra**, ARM64 (`aarch64`), Snapdragon 8 Elite / Adreno 830
* ArmadaOS Fedora-based image (test on Fedora 44 based build)
* InputPlumber 0.81.0, SDL3, toolbox `lichii-debug`
* Linux device: `/dev/dri/renderD128` was present, Vulkan reported `Adreno (TM) 830` with `turnip Mesa driver` on host
* Tested experimental binary: `~/Applications/Lichii/build-nce-fix/bin/lichii`
* Preserved snapshot: `~/Applications/Lichii/lichii-nce-first-success-20261110` and `~/Applications/Lichii/nce-first-success-20261110.patch`

**Odin 2 warning:** Original Odin 2 / Odin 2 Portal / Odin 2 Mini differ. A different Adreno GPU, firmware/kernel, driver support and memory configuration can change both compatibility and FPS. The Turnip ICD path may work when Freedreno is supplied, but confirm first with `vulkaninfo --summary` on the intended device. Never claim 60 FPS there without testing.

## A. Published fork and known-good milestone

The Odin modifications are publicly available in **[MycroftGrok/Lichii_Odin, branch `odin-armadaos`](https://github.com/MycroftGrok/Lichii_Odin/tree/odin-armadaos)**. The first verified snapshot was committed as [`64df748`](https://github.com/MycroftGrok/Lichii_Odin/commit/64df748b91d4ddbf2cfcbdd24563f5935ad82762). The *source changes* are published; a validated downloadable release binary is **not** provided yet.

The original working Odin 3 Ultra retains `~/Applications/Lichii/build-nce-fix/bin/lichii`, the `lichii-nce-first-success-20261110` binary backup, and the `nce-first-success-20261110.patch` source snapshot. These local fallback artifacts are not included in Git. Keep them intact until a replacement build has passed game and controller testing.

The source history tracks [upstream Lichii](https://github.com/zortos293/Lichii) and can merge future `nx2` updates through a separate candidate branch (section C). **Do not** replace the source tree with a fresh clone on the already-configured Odin.

## B. Exact steps for a fresh ARM64 ArmadaOS device

These instructions assume **ArmadaOS is already installed and boots successfully**. Do not flash firmware or change the bootloader to install Lichii.

1. Open Konsole. Confirm architecture and that the host Vulkan reports an Adreno GPU:

```bash
uname -m
cat /etc/os-release | grep -E '^(NAME|VERSION_ID)='
vulkaninfo --summary | grep -E 'deviceName|driverName|deviceType'
ls -l /dev/dri/renderD*
```

`uname -m` must show `aarch64`. You want `Adreno ...` and `turnip Mesa driver`, *not only* llvmpipe. If `vulkaninfo` is absent, obtain Vulkan tools using the OS's recommended package workflow; do not overwrite the host graphics stack.

2. Ensure `toolbox`, `git`, and `unzip` are installed by ArmadaOS. Clone the **published fork branch** (the repository's default branch may still be `nx2`, so the explicit `--branch` is required):

```bash
mkdir -p "$HOME/Applications/Lichii"
git clone --recurse-submodules --branch odin-armadaos \
  https://github.com/MycroftGrok/Lichii_Odin.git \
  "$HOME/Applications/Lichii/source"
cd "$HOME/Applications/Lichii/source"
git remote add upstream https://github.com/zortos293/Lichii.git
```

If `~/Applications/Lichii/source` already exists, **do not delete it**. Use the existing checkout; inspect `git status` and `git remote -v` before attempting to change branches.

3. The fork branch contains the scripts committed in section A. Run:

```bash
cd "$HOME/Applications/Lichii/source"
bash scripts/install-fresh.sh
```

The installer creates a Fedora 44 ARM64 toolbox **only if `lichii-debug` is missing**, installs development packages inside it, runs CMake/Ninja, installs a **symlink to the built executable** at `~/Applications/Lichii/bin/lichii-odin`, and creates a KDE application launcher. It doesn't mutate the host's bootc base image. Fedora/RPM Fusion packaging can change: if `dnf` cannot find a dependency (particularly FFmpeg or Qt private headers), stop at the reported error and use the current upstream [dependency guide](https://github.com/zortos293/Lichii/blob/nx2/docs/Deps.md) to resolve it. **This clean-device installer has not yet been validated end-to-end on a second handheld.**

4. For a controller not showing in Lichii, run this on the **host**:

```bash
inputplumber devices list
inputplumber device 0 targets list
sudo inputplumber device 0 targets set xbox-elite
```

On the tested Odin 3 Ultra, `device 0` was `AYN Odin 3`. Confirm the ID on *your* device before substituting it. Changing the target may momentarily disconnect the controller and may change Steam Input's default presentation. Run `inputplumber device 0 targets list` to confirm `xbox-elite`. No `chmod 666` or raw input device permission changes needed. After switching, SDL3 detected `Xbox One Elite 2 Controller`.

5. Launch from KDE's **Lichii (Odin ARM64)** application entry or Konsole:

```bash
"$HOME/Applications/Lichii/source/scripts/launch-odin.sh"
```

6. In Lichii: Emulation > Configure > Controls > Player 1: select **Pro Controller**, enable/attach it, and pick **Xbox One Elite 2 Controller**. In Graphics use **Vulkan**, Handheld mode, **No Sharpening**, `0.5x` resolution, GPU accuracy Low (if shown). Keep NCE for CPU emulation. Select only legally owned game/system files; none ship with this fork.

7. Launch a game and verify that **Lichii's own Vulkan device** is Adreno, not llvmpipe:

```bash
grep 'Report: Device:' "$HOME/.local/share/eden/log/eden_log.txt" | tail -3
```

Expected on an Odin 3 Ultra: `Device: Adreno (TM) 830`. On an Odin 2 expect a different Adreno identifier. The warnings `Could not register app ID` and `invalid nullptr parameter` were observed on the tested setup without preventing gameplay, but investigate if they correlate with a real issue.

## C. Update upstream while KEEPING Odin patches (safe candidate method)

**Never use `git reset --hard` or blindly replace the source tree.** The working branch is `odin-armadaos`; upstream is `zortos293/Lichii` branch `nx2`. Candidate builds are kept separate from the stable executable.

Once your Git worktree is clean and `odin-armadaos` is checked out:

```bash
cd "$HOME/Applications/Lichii/source"
git status --short
git switch odin-armadaos
bash scripts/update-candidate.sh
```

This fetches `upstream/nx2`, creates a dated `odin-update-YYYYMMDD-HHMMSS` branch, merges upstream there, and builds into a separate folder. It **does not replace** your `~/Applications/Lichii/bin/lichii-odin`. In case of merge conflicts, the script stops; resolve them on the candidate branch, *not* by deleting the known-good branch. Expect conflicts near the NCE timer and NSO loader code if upstream modifies those routines. Build compiler compatibility may need updating as GCC/Fedora evolves.

The script prints the full test launch command, resembling:

```bash
LICHII_BINARY="$HOME/Applications/Lichii/build-odin-update-YYYYMMDD-HHMMSS/bin/lichii" \
  "$HOME/Applications/Lichii/source/scripts/launch-odin.sh"
```

Replace the placeholder timestamp with the candidate's actual timestamp. **Test game boot, controls, and Vulkan/FPS**. If anything fails, close the candidate; the stable launcher still points to the working binary. Only when personally satisfied, promote the candidate:

```bash
cd "$HOME/Applications/Lichii/source"
bash scripts/promote-candidate.sh odin-update-YYYYMMDD-HHMMSS
git push odin-fork odin-armadaos
```

Promotion requires typing `YES`, fast-forwards `odin-armadaos` and saves the previous executable **link** to `~/Applications/Lichii/bin/lichii-odin.previous`. A candidate that needs manual conflict resolution must be committed and rebuilt before promotion. If an update turns out to have a runtime problem after promotion, launch the `.previous` executable using `LICHII_BINARY=...` while investigating; source history remains in Git.

## D. Controller persistence after reboot

On the tested Odin, switching from `deck-uhid` to `xbox-elite` worked immediately. InputPlumber / ArmadaOS may reset the target during boot, Steam mode transitions, or updates. Until a device-specific persistent profile has been verified, the **safe documented procedure** is to check `inputplumber device 0 targets list` and reapply `sudo inputplumber device 0 targets set xbox-elite` if required. We intentionally do not install an untested system service or overwrite `/usr/share/inputplumber/devices/50-ayn_odin3.yaml`.

## E. Troubleshooting

| Symptom | Check / remedy |
|---|---|
| Immediate `SIGILL` on `mrs cntpct_el0` | Verify the fork actually contains **both** the first-pass PatchManager fix and timer-handler patches; don't use an unmodified upstream binary for the local NCE test. |
| 6–16 FPS, extremely slow | `grep 'Report: Device:' ~/.local/share/eden/log/eden_log.txt`; if `llvmpipe`, use `VK_DRIVER_FILES=/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json` and retest. |
| Menus microstutter | Use `QT_QPA_PLATFORM=wayland`. |
| No controller menu entries | Check InputPlumber composite/target, switch to xbox-elite if appropriate, verify SDL3 gamepad detection. |
| Native Qt cannot launch | Ensure Qt6 Wayland plugin is installed **in the toolbox**. |
| `Unmapped InvalidateNCE @ 0x0` / guest panic | May occur from other NCE paths; review current issue logs. This is not proof of a timer regression. |
| Build fails on GCC 16 shadow warnings | Confirm the committed GCC 16 compatibility changes are present. Do not hide all compiler diagnostics. |
| Upstream merge conflicts | Do **not** force reset. Use the candidate branch and reconcile individual functions. |

## F. Known limitations and repository hygiene

The first Git snapshot is the exact milestone, potentially containing `NCE_DIAG` logging and build compatibility changes whose necessity should be re-evaluated upstream. Follow-up work should split tested functional changes into logically separate commits, remove verbose diagnostics, add automatic unit/compile checks, and confirm it still launches. Keep `src` intact, and keep the original AppImage and snapshot patch as fallback artifacts. Do not commit game dumps, firmware, keys, user configuration, caches, coredumps or compiled executables into Git.

Lichii is an independent open-source emulator project, not affiliated with AYN, Nintendo, or the ArmadaOS team. Retain upstream license and notices when publishing a fork.

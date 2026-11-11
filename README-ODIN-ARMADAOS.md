# Lichii — Odin 3 / Odin 2 ARM64 on ArmadaOS

> **Status: Odin 3 Ultra field-tested; Odin 2 experimental / not yet verified.**
> This is an install-and-maintenance *supplement* to upstream [Lichii](https://github.com/zortos293/Lichii), not a standalone emulator. The verified ARM64 modifications are published in the **`odin-armadaos` branch** of this fork. Clone that branch, not upstream `nx2`, to obtain the patches.


## One-paste installation (recommended for new ArmadaOS ARM64 devices)

Open **Konsole** on your Odin and paste this entire line:

```bash
curl -fsSL https://raw.githubusercontent.com/MycroftGrok/Lichii_Odin/odin-armadaos/scripts/install-release.sh | bash
```

The installer downloads the newest **experimental ARM64 release from this GitHub fork**, verifies its SHA-256 checksum, and creates:

- **Desktop:** a clickable **Lichii (Odin ARM64)** shortcut.
- **KDE Application Launcher → Games:** **Lichii (Odin ARM64)**.
- **Files:** an independent versioned installation under `~/Applications/Lichii/releases/`.

It automatically uses native Wayland and the Freedreno/Turnip Vulkan ICD when available. No `sudo`, build toolchain or source compilation is required for the downloadable release. ARM64 Linux libraries are packaged with the build, but the host still needs a working Vulkan driver, audio stack, and standard system libraries.

**Existing working Lichii installation?** The same installer **does not replace or switch** the active binary or its launcher. It downloads the release into a separate directory for testing and refreshes the shortcuts. This protects the already-verified 60 FPS Odin build. No source directories, game files, saves or backups are deleted. Automated releases are *pre-releases* until tested on an Odin.

If GitHub reports **no packaged Odin ARM64 release yet**, open the [fork's Actions page](https://github.com/MycroftGrok/Lichii_Odin/actions/workflows/odin-armadaos-aarch64.yml) to see whether the first ARM64 build has completed. There is no downloadable binary until the workflow succeeds.

### Add desktop and Games menu shortcuts to an existing source installation

If you already have the verified working emulator on your Odin, you only need to install the shortcuts—not download or rebuild anything:

```bash
cd "$HOME/Applications/Lichii/source" && git pull odin-fork odin-armadaos && bash scripts/install-launcher.sh
```

This preserves the active executable and installs shortcuts for the existing Wayland/toolbox launcher. The **Games** entry comes from `Categories=Game;Emulator;`, while the desktop shortcut is copied to the KDE-configured Desktop folder. If Git reports uncommitted changes, do not reset your checkout just to add shortcuts; use the existing `scripts/install-launcher.sh` after reviewing your changes.

### GitHub ARM64 releases

The isolated [Odin ARM64 GitHub Actions workflow](https://github.com/MycroftGrok/Lichii_Odin/actions/workflows/odin-armadaos-aarch64.yml) builds on native Ubuntu ARM64 and publishes a `.tar.gz`, `.AppImage` and `SHA256SUMS` as an **experimental prerelease** whenever build-related changes land on `odin-armadaos` (or when manually dispatched). It does not update the user's device automatically. A CI compile is not a replacement for on-device NCE/Vulkan/controller testing.


## Steam Integration — Switch / Switch 2 collections

The Odin fork includes a **Steam** menu (in builds that include this feature) with four ROM-import/removal commands and two artwork actions:

- **Import Switch roms to Steam**
- **Import Switch 2 roms to Steam**
- **Import all roms to Steam**
- **Clear all roms from Steam**
- **Scrape missing Steam artwork**
- **Configure SteamGridDB API key...**

The Games application menu also has a separate **Steam Integration** shortcut that runs **Import all roms to Steam**.

### One-paste shortcut setup for an existing Odin installation

Open Konsole in ArmadaOS:

```bash
cd "$HOME/Applications/Lichii/source" && git pull odin-fork odin-armadaos && bash scripts/install-launcher.sh
```

This adds **Steam Integration** to the KDE **Games** menu, installs the safe ROM launcher, and keeps the existing verified emulator binary unchanged. **Adding the native Steam menu inside Lichii requires rebuilding the Lichii application**; the menu will not appear in older executable builds.

The Steam helper discovers libraries from the Lichii `gamedirs` setting and common `Games/Switch`, `Games/Switch 2` and `Applications/Lichii/roms` folders. Add other locations explicitly:

```bash
python3 "$HOME/.local/share/lichii/tools/steam-integration.py" --mode all --rom-root "$HOME/My ROMs"
```

### Steam artwork scraping (covers, banners, backgrounds, logos, icons)

Lichii can also automatically download available artwork from [SteamGridDB](https://www.steamgriddb.com/). It fills five Steam image slots for each imported Switch or Switch 2 ROM:

| Steam artwork | SteamGridDB | Filename in Steam's grid folder |
| --- | --- | --- |
| Portrait cover | 600×900 grid | `<appid>p.png` |
| Landscape cover | 920×430 / 460×215 grid | `<appid>.png` |
| Game details background | Hero | `<appid>_hero.png` |
| Transparent game title | Logo | `<appid>_logo.png` |
| Game icon | Icon | `<appid>_icon.png` |

Accepted file formats also include `.jpg` for covers/backgrounds and `.ico` for icons when the artwork provider supplies those. Artwork lives in the active Steam user's `userdata/<id>/config/grid/` directory.

**First-time setup:** A SteamGridDB API key is required. Create a free account and generate your own key at [SteamGridDB API preferences](https://www.steamgriddb.com/profile/preferences/api). Do **not** post the key in GitHub or ChatGPT. In a new Lichii build, open **Steam → Configure SteamGridDB API key...**, paste the key in the hidden entry field, and confirm. It is stored **only on the Odin**, in `~/.config/lichii/steamgriddb-api-key` with owner-only permissions.

Or configure it using a single Konsole command (the key input is hidden):

```bash
python3 "$HOME/.local/share/lichii/tools/steam_artwork.py" --configure
```

Once the key is configured, **importing ROMs automatically downloads artwork** for any imported games that are missing it. To scrape artwork for games you've *already* added to Steam, select **Steam → Scrape missing Steam artwork** or run:

```bash
python3 "$HOME/.local/share/lichii/tools/steam-integration.py" --mode artwork
```

**Safety:** The scraper uses exact game-title matches and skips ambiguous or missing results rather than picking the wrong game. It downloads only static PNG/JPEG images and ICO icons from SteamGridDB's HTTPS CDN. It does **not** replace existing or manually customized Steam artwork, and it does not modify ROM contents or emulator saves. If no API key is available, ROM imports still work; only artwork downloads are skipped. Some games may lack certain types of artwork. Steam must be fully closed when importing or scraping. If the client is running in the background, Lichii now identifies the specific Steam processes and offers to request their shutdown **only after you approve**. This can interrupt Steam games or downloads. If Steam will not exit, the helper aborts without modifying Steam metadata; it never uses SIGKILL.


To diagnose an apparently closed Steam client without changing anything:

```bash
python3 "$HOME/.local/share/lichii/tools/steam-integration.py" --check-steam
```

The check prints the current user's Steam process names and PIDs (exit code 3 means
Steam processes are still present). Lichii's Steam menu prompts for shutdown if
it sees any. From Konsole only, you may opt in with
`--shutdown-steam` on an import or artwork command; the helper first
tries Steam's normal `-shutdown` command if available, then sends SIGTERM
only to recognized current-user Steam processes. It rechecks before writing
Steam metadata, and stops if Steam remains running. Nothing is shut down
silently, and the integration doesn't restart Steam afterward.

### How it works

Steam **must be fully closed** before importing or clearing games. Steam overwrites its shortcuts while running. The helper reads existing Steam `shortcuts.vdf` entries and the newer collection data from `cloud-storage-namespace-1.json`, backs up the original Steam metadata, then modifies only what is necessary. Collections are named exactly **Switch** and **Switch 2**. If those collections already exist, they are reused.

Each imported title is a separate non-Steam shortcut pointing to the Lichii game wrapper; it starts **native Wayland Lichii with `-f -g "<ROM path>"`**, so fullscreen is requested and Lichii's existing per-game configuration remains intact. Steam's Proton compatibility override should remain off for this native launcher.

Switch 1 and Switch 2 formats can overlap (`.nsp` and `.xci` do not identify a generation). The **Import all** action classifies games by the names of folders such as `Switch` and `Switch 2`; `.nup` is recognized as Switch 2. Unclassified games are **reported and skipped**, rather than incorrectly assigned. A generation-specific menu action assigns ambiguous games to the requested platform, but skips files clearly labeled as the other platform. Supported extensions include `.nsp`, `.xci`, `.nsz`, `.xcz`, `.nup` and `.nro`. Explicitly named **DLC**, **update**, **patch** and **unlocker** files (or content placed in DLC/update directories) are skipped because they are not independent games. This is filename-based safety filtering, not full ROM metadata classification; review the dry run and keep ambiguous titles out of Steam until verified.

Repeated imports are **idempotent**: existing ROM paths are reused and games already in the correct collection are not duplicated. **Clear all roms from Steam** removes only entries created by this Lichii integration and removes their memberships; it preserves ROM files, emulator saves and settings, third-party Steam shortcuts and unrelated collections. Steam-metadata backups are stored under `~/.local/share/lichii/steam-integration-backups/`.

For a read-only preview, run:

```bash
python3 "$HOME/.local/share/lichii/tools/steam-integration.py" --mode all --dry-run
```

The helper currently requires one identifiable Steam installation and one local signed-in Steam account, with Steam's modern cloudstorage collections files initialized. For multiple Steam profiles or an unrecognized format, it **stops without modifying Steam files**. Steam Flatpak permissions and Steam's cloud collection reconciliation must be tested on the target device; an offline test is not proof the live Steam UI will accept the edits. Backups are produced before modifications, so issues can be rolled back.


### Test the compiled Steam menu safely on an already-working Odin

The **Steam** menu is part of the Qt GUI executable and requires an ARM64 build;
running the Python helper alone does not add it to an older Lichii binary.

On an Odin 3 Ultra that has the working Fedora toolbox **lichii-debug** and the
feature checkout **odin-steam-preview**, paste the following into Konsole:

```bash
cd "$HOME/Applications/Lichii/source" &&
git pull --ff-only odin-fork feature/steam-integration-switch-collections-20261110 &&
bash scripts/build-steam-menu-test.sh
```

This compiles the GUI target in an independent
`~/Applications/Lichii/build-steam-menu-test/` directory, uses the existing
toolbox and known-working Wayland/Turnip launch script, and installs a separate
**Games → Lichii (Steam Menu Test)** entry and desktop shortcut. It **does not
rebuild, delete, replace, or relink the stable Lichii executable**, and verifies
the stable executable's SHA-256 did not change.

After a successful build you may launch the test independently using:

```bash
"$HOME/.local/bin/lichii-steam-menu-test"
```

Check that the test GUI exposes **Steam → Configure SteamGridDB API key...**,
then test game loading and the Steam shortcut workflow. Steam must be fully
closed before the Steam metadata import or artwork scraping actions. **Do not
promote this experimental build until it works on-device.** If the compiler
fails, share the exact error output; the stable launcher remains available.

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

The Odin modifications are publicly available in **[MycroftGrok/Lichii_Odin, branch `odin-armadaos`](https://github.com/MycroftGrok/Lichii_Odin/tree/odin-armadaos)**. The first verified snapshot was committed as [`64df748`](https://github.com/MycroftGrok/Lichii_Odin/commit/64df748b91d4ddbf2cfcbdd24563f5935ad82762). The *source changes* are published; experimental automated ARM64 downloads are available after the GitHub release workflow completes successfully. On-device validation remains necessary.

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

2. Ensure `toolbox`, `git`, and `unzip` are installed by ArmadaOS. Clone the **published fork branch** (the explicit `--branch` keeps the intended patch set even if repository defaults change):

```bash
mkdir -p "$HOME/Applications/Lichii"
git clone --recurse-submodules --branch odin-armadaos \
  https://github.com/MycroftGrok/Lichii_Odin.git \
  "$HOME/Applications/Lichii/source"
cd "$HOME/Applications/Lichii/source"
git remote add upstream https://github.com/zortos293/Lichii.git
```

If `~/Applications/Lichii/source` already exists, **do not delete it**. Use the existing checkout; inspect `git status` and `git remote -v` before attempting to change branches.

3. The fork branch contains the installer and maintenance scripts. Run:

```bash
cd "$HOME/Applications/Lichii/source"
bash scripts/install-fresh.sh
```

The **source-build fallback** installer creates a Fedora 44 ARM64 toolbox **only if `lichii-debug` is missing**, installs development packages inside it, runs CMake/Ninja, installs a **symlink to the built executable** at `~/Applications/Lichii/bin/lichii-odin`, and creates a KDE application launcher. It doesn't mutate the host's bootc base image. Fedora/RPM Fusion packaging can change: if `dnf` cannot find a dependency (particularly FFmpeg or Qt private headers), stop at the reported error and use the current upstream [dependency guide](https://github.com/zortos293/Lichii/blob/nx2/docs/Deps.md) to resolve it. **This clean-device installer has not yet been validated end-to-end on a second handheld.**

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
git push odin-fork odin-armadaos   # Original Odin checkout; fresh clones normally use 'origin'
```

Promotion requires typing `YES` and fast-forwards `odin-armadaos`. It copies the tested executable into an independent versioned folder under `~/Applications/Lichii/releases/`, verifies the copy, and atomically updates the stable launcher. Before switching, it saves a verified **copy of the previous executable's bytes** under `~/Applications/Lichii/backups/` and links `~/Applications/Lichii/bin/lichii-odin.previous` to that independent copy. A candidate that needs manual conflict resolution must be committed and rebuilt before promotion. If a promoted update has a runtime problem, use the previously verified copy:

```bash
LICHII_BINARY="$HOME/Applications/Lichii/bin/lichii-odin.previous" \\
  "$HOME/Applications/Lichii/source/scripts/launch-odin.sh"
```

The ordinary `build-deploy.sh` path also snapshots before rebuilding. If the build would otherwise overwrite the current stable executable, it parks the launcher on a verified backup first, then deploys an independent, checked copy. **These safety protections have not yet been exercised end-to-end on an Odin 2 or a clean Odin 3 installation.**

### Which Git remote should you push to?

On the original developer's Odin, the fork remote is named `odin-fork` and upstream Lichii is `origin`. On a clean clone of this fork, the fork is usually `origin` and upstream Lichii is `upstream`. Check with `git remote -v` before choosing a push target. `scripts/update-candidate.sh` accepts either the verified `upstream` remote or the original Odin's verified `origin` remote for fetching `zortos293/Lichii` updates. It will stop if it cannot verify the source.

**Always run `git status --short` and `bash -n scripts/*.sh` before experimenting. Never run `build-deploy.sh` just to verify that a currently working binary still launches; use the existing launcher instead.**

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

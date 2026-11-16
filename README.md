<!--
# SPDX-FileCopyrightText: Copyright 2025 Eden Emulator Project
# SPDX-License-Identifier: GPL-3.0-or-later

# SPDX-License-Identifier: GPL-2.0-or-later
-->

> [!IMPORTANT]
> **Odin 3 Ultra / ArmadaOS:** The [experimental NX2 ARM64 release](https://github.com/MycroftGrok/Lichii_Odin/releases/tag/odin3-nx2-armadaos-20261115-v1) is publicly available, with a [verified-package installer and setup notes](README-ODIN-NX2.md). For background on Turnip/Wayland, NCE and controllers, see the [Odin guide](README-ODIN-ARMADAOS.md).
> **Tested:** Odin 3 Ultra running ArmadaOS; 60 FPS observed in one game. **Odin 2 remains untested.** This fork is independent of upstream Lichii; the original project is at [zortos293/Lichii](https://github.com/zortos293/Lichii).

<h2 align="center">⚠️ Lichii has no official website ⚠️</h2>

> [!CAUTION]
> **Independent fork:** This repository is an unofficial Odin/ArmadaOS fork. Obtain its experimental builds from [this fork's releases](https://github.com/MycroftGrok/Lichii_Odin/releases); for upstream releases, use [zortos293/Lichii](https://github.com/zortos293/Lichii/releases). Neither project endorses third-party 'Lichii' download websites; see upstream [security warning #545](https://github.com/zortos293/Lichii/issues/545).

<p align="center">
  <img src="dist/branding/lichii_icon_with_logo.png" alt="Lichii" width="600">
</p>

# Lichii

Lichii is an experimental, open-source Nintendo Switch and Switch 2 emulator written in C++. It builds on Eglantine, Eden, yuzu and Sudachi, preserving their contributions while developing this fork's game compatibility and renderer fixes.

This is an independent fork, not an official release of those upstream projects. Lichii is not affiliated with Nintendo.

Visit the [Lichii game compatibility website](https://lichii.zortos.me) to find games and compare community compatibility reports.

## Downloads and setup

### Odin 3 Ultra / ArmadaOS ARM64 (experimental NX2)

Get [NX2 release v1](https://github.com/MycroftGrok/Lichii_Odin/releases/tag/odin3-nx2-armadaos-20261115-v1), download `install-nx2-odin.py` from **Assets**, and run:

```bash
python3 "$HOME/Downloads/install-nx2-odin.py"
```

The installer verifies the published archive checksum and executable hash, installs into a release-specific directory, and **never replaces an existing working executable**. The first-install path requires an existing Fedora ARM64 `lichii-debug` Toolbox with compatible runtime dependencies; it does not provision those dependencies. See [NX2 installation instructions](README-ODIN-NX2.md) and the [ArmadaOS guide](README-ODIN-ARMADAOS.md). A clean ARM64 runner tests isolated installation and reinstall preservation, but an actual fresh-device ArmadaOS test remains outstanding. Odin 2 is untested.

Lossless Scaling requires your own Steam installation of Lossless Scaling; its proprietary `Lossless.dll` is not distributed. The provided launcher can locate that DLL in the standard Steam library.

The earlier `odin-armadaos-build-*` releases remain available for historical compatibility, but are not the NX2 package.

On Windows, extract the entire build archive and run **lichii.exe**. Only use games and system files you have legally obtained. Games, keys and firmware are not included.

### Existing saves and settings

Lichii uses its own profile: `%APPDATA%\lichii` on Windows, and the `lichii` directories under `$XDG_DATA_HOME`, `$XDG_CONFIG_HOME` and `$XDG_CACHE_HOME` on Linux and macOS. Without XDG overrides, these are `~/.local/share/lichii`, `~/.config/lichii` and `~/.cache/lichii`. An existing portable `user/` directory still takes priority and is not imported or changed by the wizard.

On the first non-portable GUI launch, Lichii offers to import Eden and other detected emulator profiles. Back up `%APPDATA%\eden` first on Windows, or the old data, config and cache directories on Unix, and close the source emulator. Choose **Keep Old Data** to copy without changing the source, then check your saves and relaunch. Existing destination data is retained in backup directories rather than merged. Move also retains a source backup until you remove it yourself; Link deliberately shares settings and saves. Paths outside the imported data root remain shared and unchanged. An interrupted import offers recovery on the next launch. `eden-cli`, including `--help` and `--version`, refuses to initialize configuration until you import or explicitly choose **Start fresh** in the GUI.

## Compatibility and issue reports

Compatibility and performance vary by game, hardware and driver. Rendering errors, stutters and crashes remain possible. Passing automated tests does not establish that a game renders correctly, and this project makes no universal frame-rate guarantee.

Browse [community compatibility reports](https://lichii.zortos.me/reports) for results with each player's build and setup.

Desktop reporting requires a build containing [PR #303](https://github.com/zortos293/Lichii/pull/303) and is not available in build 88. In builds that include it, play and stop a Switch 2 game, then right-click that game and choose **Submit compatibility report**. Only the latest session in the current Lichii process is eligible.

Confirm the matching website catalog entry and review the editable machine, game, setup, and enabled add-on details prefilled where available. Check the public preview and give explicit consent before submitting. Nothing uploads automatically, and the native v1 reporter does not read or upload logs or files.

When [reporting an issue](https://github.com/zortos293/Eglantine/issues), include:

- The exact build, game version, CPU, GPU and driver version.
- Relevant settings and steps to reproduce the problem.
- A screenshot and the log from the affected session, after checking it for personal information.

Do not upload game files, keys, firmware or private account information.

## Building and contributing

See the [build guide](docs/Build.md), [user documentation](docs/user/README.md) and [coding guidelines](docs/Coding.md). Some inherited documentation and internal build target names still use upstream names. The GUI build target is `lichii`; its output is `lichii.exe` on Windows and `lichii` on other desktop platforms.

Keep changes focused and distinguish code-level checks from actual gameplay testing.

## Artwork
Art created by YOB (yobslab)
The supplied Lichii logo, icon and library artwork are in [dist/branding](dist/branding). Windows, Linux and macOS icon resources are generated from that artwork by [Generate-LichiiIcons.ps1](tools/Generate-LichiiIcons.ps1).

## Support Lichii

Lichii is free and stays free. If you want to help, you can donate in crypto. Donations help pay for the AI tools and build machines used to develop this open-source project faster.

**Solana (SOL)**
```text
JepEjfyWjGjhJvHSrqj52KtLjcbbbmUh1iGqerYBF4w
```

**Ethereum (ETH)**
```text
0x055ABa1b80Bc35C836Ce7E9F47c2b3d6C75b5534
```

**Bitcoin (BTC)**
```text
bc1qcvxdpf4qvdhqp8ee4s355cjmxrzsphsdwpl8w4
```

**BNB Smart Chain (BNB)**
```text
0x055ABa1b80Bc35C836Ce7E9F47c2b3d6C75b5534
```

**Polygon**
```text
0x055ABa1b80Bc35C836Ce7E9F47c2b3d6C75b5534
```

Send each coin on its matching network. Coins sent on the wrong network can't be recovered.

> [!NOTE]
> Donations are voluntary gifts and are non-refundable. A donation does not buy any product, service, perk, early access, exclusive build, priority support or say in the project. Every release stays free and public for everyone.

## Credits and license

Lichii inherits the work of the Eglantine, Eden, yuzu and Sudachi projects and their contributors, including Eglantine's original developer Camille LaVey. Original copyright notices and third-party licenses are retained.

See [LICENSE.txt](LICENSE.txt) and the source files for applicable license terms.

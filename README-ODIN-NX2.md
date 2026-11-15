# Lichii NX2 for Odin 3 Ultra / ArmadaOS

Experimental ARM64 release for Odin 3 Ultra on Fedora-based ArmadaOS. This is an independent community fork, not an official upstream Lichii build.

## Install

Requires ArmadaOS, Python 3 and a prepared `lichii-debug` Fedora Toolbox with Lichii's runtime Qt/Vulkan dependencies. Fresh-install dependency provisioning has **not** been tested.

Download `install-nx2-odin.py` from the release assets, then run `python3 install-nx2-odin.py`. The installer verifies SHA256SUMS, stages a release, and leaves any existing Lichii installation untouched. First-time installs create the normal launcher and attempt to fetch the matching public source for Steam menu scripts.

If no `lichii-debug` Toolbox exists, create one and install the compatible Fedora aarch64 Lichii runtime dependencies before running the installer. See `scripts/install-fresh.sh` for the project's tested development dependency list; it builds from source and is not required for downloading this binary.

## Lossless Scaling

Lichii can read `Lossless.dll` from your separately installed Steam Lossless Scaling application. The launcher automatically restores a missing DLL when Steam uses the default library path. The proprietary DLL is not included.

## Safety and compatibility

No ROMs, keys, firmware or saved data are included. Odin 2 and other ARM64 devices have not been validated. Compatibility and FPS vary.

Release: https://github.com/MycroftGrok/Lichii_Odin/releases/tag/odin3-nx2-armadaos-20261115-v1
Source branch: https://github.com/MycroftGrok/Lichii_Odin/tree/release/odin3-nx2-armadaos-20261115

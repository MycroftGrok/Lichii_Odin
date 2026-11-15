# Lichii NX2 for Odin 3 Ultra / ArmadaOS

Experimental ARM64 release for Odin 3 Ultra on Fedora-based ArmadaOS. This is an independent community fork, not an official upstream Lichii build.

## Install

Requires ArmadaOS, Python 3 and a prepared `lichii-debug` Fedora Toolbox with Lichii's runtime Qt/Vulkan dependencies. Fresh-install dependency provisioning has **not** been tested.

Download `install-nx2-odin.py` from the release assets, then run `python3 install-nx2-odin.py`. The installer verifies SHA256SUMS, stages a release, and leaves any existing Lichii installation untouched. First-time installs create the normal launcher and attempt to fetch the matching public source for Steam menu scripts.

If no `lichii-debug` Toolbox exists, create one and install the compatible Fedora aarch64 Lichii runtime dependencies before running the installer. See `scripts/install-fresh.sh` for the project's tested development dependency list; it builds from source and is not required for downloading this binary.

## One-command ArmadaOS bootstrap (feature candidate)

The optional bootstrap script will create a Fedora 44 lichii-debug Toolbox on a compatible
ARM64 ArmadaOS host if it is missing, install runtime packages **inside the Toolbox only**,
download the fixed v1 release installer (SHA-256 pinned), and let that installer verify
the release archive and executable. The host must already provide Python 3, Podman,
and Fedora Toolbx. A missing host Toolbox executable is reported rather than modifying
the bootc/immutable host OS.

Until the bootstrap pull request passes review, obtain the development version directly
from [its feature branch](https://github.com/MycroftGrok/Lichii_Odin/tree/feature/odin-nx2-one-command-bootstrap-20261115):

```bash
curl -fsSL --proto '=https' --tlsv1.2 \
  -o "$HOME/Downloads/bootstrap-odin-nx2.py" \
  "https://raw.githubusercontent.com/MycroftGrok/Lichii_Odin/feature/odin-nx2-one-command-bootstrap-20261115/scripts/bootstrap-odin-nx2.py" &&
python3 "$HOME/Downloads/bootstrap-odin-nx2.py" --install
```

For a **read-only inspection** of an existing Odin installation, use the same download
and replace `--install` with `--diagnose`. Existing working executables and
source checkouts are never overwritten; an already-installed Lichii skips all provisioning.

`--repair` restores **only a missing** Lossless.dll from the user's
existing default Steam Lossless Scaling installation. It does not install or
redistribute Lossless Scaling.

The installer does not compile code, change the host OS, reconfigure InputPlumber
or install proprietary DLLs from the internet. No ROMs, firmware, keys, saves,
Steam artwork, or emulation settings are modified. Some GPUs and non-standard
Steam library locations may require separate setup.

**Validation:** Offline ARM64 tests cover preservation, integrity checks,
safety, and the commands used for Fedora package provisioning. The v1
release installer has already passed an isolated ARM64 first-install/
reinstall smoke test. A genuinely fresh Odin/ArmadaOS device has not
yet been validated end to end. An existing Toolbox with a non-Fedora-44
image is left alone and treated as an error, not silently replaced.

## Lossless Scaling

Lichii can read `Lossless.dll` from your separately installed Steam Lossless Scaling application. The launcher automatically restores a missing DLL when Steam uses the default library path. The proprietary DLL is not included.

## Safety and compatibility

No ROMs, keys, firmware or saved data are included. Odin 2 and other ARM64 devices have not been validated. Compatibility and FPS vary.

Release: https://github.com/MycroftGrok/Lichii_Odin/releases/tag/odin3-nx2-armadaos-20261115-v1
Source branch: https://github.com/MycroftGrok/Lichii_Odin/tree/release/odin3-nx2-armadaos-20261115

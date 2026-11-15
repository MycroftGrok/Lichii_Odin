#!/usr/bin/env python3
"""Odin 3 Ultra/ArmadaOS one-command Lichii NX2 setup (standard library only).

Modes:
  --install   Provision a Fedora 44 Toolbox, then install verified published NX2.
  --diagnose  Read-only environment, link, library, and controller checks.
  --repair   Restore a missing LSFG DLL from the user's own Steam installation.

No source compilation. No modification of the Fedora/ArmadaOS immutable host.
Never deletes or replaces a working emulator, saves, games, keys, or Steam data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

BOX = "lichii-debug"
IMAGE = "registry.fedoraproject.org/fedora-toolbox:44"
REPO = "MycroftGrok/Lichii_Odin"
TAG = "odin3-nx2-armadaos-20261115-v1"
ASSET = "install-nx2-odin.py"
# Pin the reviewed release installer. Changed assets are rejected.
ASSET_SHA256 = "43789dacc02eb6ea737c4142f3d18edadf0f6891498380283c98a98c88c7badc"
USER_AGENT = "Odin-NX2-Bootstrap/1.0"
HOME = Path.home()
ROOT = HOME / "Applications/Lichii"
ACTIVE = ROOT / "bin/lichii-odin"
DLL = HOME / ".local/share/lichii/lossless/Lossless.dll"
STEAM_DLL = HOME / ".local/share/Steam/steamapps/common/Lossless Scaling/Lossless.dll"
ICD = Path("/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json")

# Runtime-only Fedora 44 packages. Do not install compilers or SDKs on the host.
FEDORA_RUNTIME = (
    "git", "qt6-qtbase-gui", "qt6-qtwayland", "qt6-qtmultimedia",
    "qt6-qtcharts", "qt6-qtsvg", "SDL3", "vulkan-loader",
    "mesa-vulkan-drivers", "libusb1", "openssl-libs", "zlib-ng-compat",
    "libzstd", "lz4-libs", "boost-context", "boost-fiber", "opus",
    "libavcodec-free", "libavformat-free", "libavutil-free",
    "libavfilter-free", "libswscale-free", "libxkbcommon-x11", "libglvnd-opengl",
)


def die(message: str) -> None:
    raise SystemExit("STOP: " + message)


def run(*cmd: str, timeout: int = 120, check: bool = True, capture: bool = False):
    return subprocess.run(
        list(cmd), check=check, timeout=timeout, text=True,
        stdin=subprocess.DEVNULL,
        **({"capture_output": True} if capture else {}),
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def working_installation() -> bool:
    if ACTIVE.is_symlink():
        if not ACTIVE.exists():
            die("Existing active emulator symlink is broken; no changes made")
        target = ACTIVE.resolve()
        if not target.is_file() or not os.access(target, os.X_OK):
            die("Existing active emulator target is not executable; no changes made")
        return True
    if ACTIVE.exists():
        die("Emulator path already exists but is not a symlink; no changes made")
    return False


def toolbox_names(output: str) -> set[str]:
    # Compare complete tokens so 'lichii-debug-old' is never mistaken for BOX.
    return {token for row in output.splitlines() for token in row.split()}


def has_box() -> bool:
    if not shutil.which("toolbox"):
        return False
    result = run("toolbox", "list", "--containers", capture=True, check=False, timeout=30)
    if result.returncode:
        die("Cannot inspect Toolbox containers: " + result.stderr[-500:])
    return BOX in toolbox_names(result.stdout)


def box_version() -> str:
    result = run(
        "toolbox", "run", "--container", BOX, "sh", "-c",
        '. /etc/os-release; printf "%s:%s\\n" "$ID" "$VERSION_ID"',
        capture=True, check=False, timeout=90,
    )
    if result.returncode:
        die("Cannot inspect existing Toolbox OS: " + result.stderr[-500:])
    rows = result.stdout.strip().splitlines()
    if not rows:
        die("Toolbox OS metadata is empty; refusing package changes")
    return rows[-1].strip()


def ensure_box() -> None:
    if not shutil.which("toolbox"):
        die("ArmadaOS Toolbx is not installed. This installer does not modify the immutable host.")
    if not has_box():
        print(f"=== CREATE {BOX} TOOLBOX (Fedora 44 ARM64) ===", flush=True)
        run("toolbox", "--assumeyes", "create", "--container", BOX, "--image", IMAGE, timeout=900)
        if not has_box():
            die("Toolbox creation did not produce the expected container")
    version = box_version()
    if version != "fedora:44":
        die(f"Refusing to modify {BOX}: expected Fedora 44, got {version!r}")
    print("PASS: Fedora 44 Toolbox confirmed", flush=True)


def install_dependencies() -> None:
    print("=== INSTALL ARM64 RUNTIME DEPENDENCIES INSIDE TOOLBOX ===", flush=True)
    run("toolbox", "run", "--container", BOX, "sudo", "dnf", "install", "-y",
        *FEDORA_RUNTIME, timeout=1800)
    print("PASS: Toolbox package installation completed", flush=True)


def fetch_installer(target: Path) -> None:
    endpoint = f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}"
    request = urllib.request.Request(endpoint, headers={
        "User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=45) as reply:
        info = json.load(reply)
    if info.get("draft") or info.get("tag_name") != TAG:
        die("Expected published NX2 prerelease not found")
    found = [a for a in info.get("assets", []) if a.get("name") == ASSET]
    if len(found) != 1:
        die("Expected exactly one install-nx2-odin.py release asset")
    asset = found[0]
    url = asset.get("browser_download_url", "")
    if url != f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}":
        die("Unexpected installer download URL")
    if asset.get("digest") not in (None, "sha256:" + ASSET_SHA256):
        die("GitHub asset SHA-256 differs from the pinned installer")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as reply, target.open("xb") as out:
        shutil.copyfileobj(reply, out)
    if sha256(target) != ASSET_SHA256:
        die("Pinned NX2 installer SHA-256 verification failed; nothing installed")
    print("PASS: Official NX2 installer SHA-256 verified", flush=True)


def ensure_source_checkout() -> None:
    """Preserve an existing checkout, or fetch only the matching public tag."""
    destination = ROOT / "source"
    if destination.is_symlink():
        print("WARNING: Existing source checkout symlink; not replacing it.")
        return
    if destination.exists():
        print("PRESERVED: Existing Lichii source checkout.")
        return
    print("=== FETCH MATCHING PUBLIC NX2 SOURCE HELPERS ===", flush=True)
    clone = run(
        "toolbox", "run", "--container", BOX, "git", "clone", "--depth", "1",
        "--branch", TAG, f"https://github.com/{REPO}.git", str(destination),
        timeout=1200, check=False, capture=True,
    )
    if clone.returncode or not (destination / "scripts/launch-odin.sh").is_file():
        print("WARNING: Optional source checkout unavailable; installed emulator is preserved.")
        print("Git output:", clone.stderr[-500:])
    else:
        print("PASS: Matching public source and Steam GUI helper scripts present.")


def install() -> None:
    if platform.machine() != "aarch64":
        die("This installer supports ARM64/aarch64 only")
    print("=== LICHII NX2 ONE-COMMAND INSTALL ===", flush=True)
    if working_installation():
        print("PRESERVED: Lichii already installed. No downloads or modifications made.")
        print("Run --diagnose to inspect your installation (read-only).")
        return
    if not ICD.is_file():
        print("WARNING: Turnip Vulkan ICD missing on the host: " + str(ICD))
        print("Hardware rendering may need ArmadaOS/Turnip configuration.")
    ensure_box()
    install_dependencies()
    with tempfile.TemporaryDirectory(prefix="lichii-nx2-bootstrap-") as tmp:
        installer = Path(tmp) / ASSET
        print("=== VERIFY RELEASE INSTALLER ===", flush=True)
        fetch_installer(installer)
        print("=== INSTALL VERIFIED NX2 RELEASE ===", flush=True)
        # The verified release installer performs its own tarball, binary,
        # runtime checks, and refuses to replace any installed emulator.
        run(sys.executable, str(installer), timeout=900)
    if working_installation():
        ensure_source_checkout()
        print("PASS: Verified NX2 installed and source helpers checked.")
    else:
        print("WARNING: No active executable was installed; see runtime error output.")
    diagnose()


def diagnose() -> None:
    print("=== LICHII NX2 READ-ONLY DIAGNOSTICS ===", flush=True)
    print("Architecture:", platform.machine())
    print("Turnip ICD:", "FOUND" if ICD.is_file() else "MISSING", ICD)
    print("Toolbox command:", "FOUND" if shutil.which("toolbox") else "MISSING")
    present = has_box()
    print("Toolbox container:", "FOUND" if present else "MISSING", BOX)
    if present:
        print("Toolbox OS:", box_version())
    if ACTIVE.is_symlink():
        print("Active executable:", ACTIVE.resolve() if ACTIVE.exists() else "BROKEN SYMLINK")
        active = ACTIVE.resolve()
        if active.is_file() and present:
            probe = run("toolbox", "run", "--container", BOX, "ldd", str(active),
                        check=False, capture=True, timeout=60)
            unresolved = [line.strip() for line in probe.stdout.splitlines() if "not found" in line]
            print("Runtime libraries:", "PASS" if probe.returncode == 0 and not unresolved else "CHECK")
            for line in unresolved[:20]:
                print(" MISSING:", line)
    else:
        print("Active executable:", "NON-SYMLINK" if ACTIVE.exists() else "NOT INSTALLED")
    print("LSFG DLL:", "FOUND" if DLL.is_file() else "MISSING (optional)")
    print("Steam Lossless.dll:", "FOUND" if STEAM_DLL.is_file() else "MISSING (optional)")
    print("InputPlumber:", "FOUND" if shutil.which("inputplumber") else "not on host PATH")
    print("No files modified by diagnostics.")


def repair_lossless() -> None:
    print("=== REPAIR MISSING LOSSLESS SCALING DLL ===", flush=True)
    if DLL.exists() or DLL.is_symlink():
        print("PRESERVED: Existing LSFG path present; never overwrite it.")
        return
    if not STEAM_DLL.is_file() or STEAM_DLL.is_symlink():
        print("SKIPPED: No locally owned Steam Lossless Scaling DLL found.")
        return
    with STEAM_DLL.open("rb") as stream:
        if stream.read(2) != b"MZ":
            die("Steam DLL has invalid Windows PE header")
    folder = DLL.parent
    if folder.is_symlink():
        die("LSFG destination is a symlink; refusing to write")
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=folder, prefix=".Lossless-", delete=False) as temp:
        temporary = Path(temp.name)
        try:
            with STEAM_DLL.open("rb") as orig:
                shutil.copyfileobj(orig, temp)
            temp.flush()
            os.fsync(temp.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        if sha256(temporary) != sha256(STEAM_DLL):
            die("LSFG DLL copied bytes differ from source")
        os.link(temporary, DLL)  # O_EXCL equivalent: never replace a user file.
        DLL.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)
    print("PASS: Missing LSFG DLL restored from your Steam installation.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--install", action="store_true", help="Fresh safe one-command install")
    options.add_argument("--diagnose", action="store_true", help="Read-only environment checks")
    options.add_argument("--repair", action="store_true", help="Restore only a missing LSFG DLL")
    args = parser.parse_args()
    if args.install:
        install()
    elif args.diagnose:
        diagnose()
    else:
        repair_lossless()


if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            OSError, ValueError, urllib.error.URLError) as err:
        die(str(err))

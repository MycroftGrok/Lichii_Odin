#!/usr/bin/env python3
"""Install a verified experimental Lichii NX2 ARM64 release from MycroftGrok/Lichii_Odin.

Preserves existing installed Lichii without any automatic activation.
No keys, games, firmware, or Lossless.dll are downloaded or distributed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

REPO = "MycroftGrok/Lichii_Odin"
TAG = "odin3-nx2-armadaos-20261115-v1"
ARCHIVE = "lichii-odin3-nx2-armadaos-aarch64.tar.gz"
MANIFEST = "SHA256SUMS"
BINARY_SHA256 = "a1e7408f605a05c3fe636e09fab410f3909eee3e676163754a6d2fb2edd50977"
USER_AGENT = "Lichii-Odin3-NX2-Installer/1.0"
ROOT = Path.home() / "Applications/Lichii"
RELEASE = ROOT / "releases" / TAG
LINK = ROOT / "bin/lichii-odin"
LAUNCHER = Path.home() / ".local/bin/lichii-odin"
DESKTOP = Path.home() / ".local/share/applications/lichii-odin.desktop"
TOOLS = Path.home() / ".local/share/lichii/tools"


def die(message):
    raise SystemExit("STOP: " + message)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for piece in iter(lambda: f.read(1024 * 1024), b""):
            h.update(piece)
    return h.hexdigest()


def get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as f:
        return json.load(f)


def download(url, target):
    if not url.startswith("https://github.com/" + REPO + "/releases/download/" + TAG + "/"):
        die("Untrusted release asset URL")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as inp, open(target, "xb") as out:
        shutil.copyfileobj(inp, out)


def run(*cmd, **kwargs):
    return subprocess.run(cmd, check=True, **kwargs)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    if platform.machine() != "aarch64":
        die("Requires an ARM64/aarch64 device")
    if not shutil.which("toolbox"):
        die("ArmadaOS toolbox is needed. Install toolbox and prepare the lichii-debug container before installing.")
    boxes = subprocess.run(["toolbox", "list", "--containers"], capture_output=True, text=True, timeout=30)
    if boxes.returncode or "lichii-debug" not in boxes.stdout:
        die("The lichii-debug Toolbox isn't ready. See README-ODIN-NX2.md for setup instructions.")
    if LINK.is_symlink() and LINK.exists():
        print("An existing working Lichii is installed. It will NOT be replaced.")
    elif (LINK.exists() or LINK.is_symlink()) and not LINK.is_symlink():
        die("Existing Lichii launcher path is not a symlink; will not replace it")
    print("Looking up official experimental release from this Odin fork:", TAG, flush=True)
    release = get_json(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}")
    if release.get("draft") or release.get("tag_name") != TAG:
        die("Expected published release was not found")
    assets = {x["name"]: x for x in release.get("assets", [])}
    if ARCHIVE not in assets or MANIFEST not in assets:
        die("Archive or checksum asset is missing")
    ROOT.joinpath("releases").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".nx2-download-", dir=ROOT / "releases") as directory:
        tmp = Path(directory)
        download(assets[MANIFEST]["browser_download_url"], tmp / MANIFEST)
        content = (tmp / MANIFEST).read_text()
        expected = None
        for line in content.splitlines():
            pieces = line.strip().split()
            if len(pieces) == 2 and pieces[1].lstrip("*") == ARCHIVE:
                expected = pieces[0]
        if not expected or len(expected) != 64 or any(x not in "0123456789abcdefABCDEF" for x in expected):
            die("Invalid SHA256SUMS manifest")
        download(assets[ARCHIVE]["browser_download_url"], tmp / ARCHIVE)
        if sha(tmp / ARCHIVE).lower() != expected.lower():
            die("Archive SHA-256 mismatch — nothing installed")
        print("PASS: Release archive checksum verified")
        staging = tmp / "unpack"
        staging.mkdir()
        with tarfile.open(tmp / ARCHIVE, "r:gz") as archive:
            for entry in archive:
                p = Path(entry.name)
                if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0] != "lichii":
                    die("Unsafe archive path: " + entry.name)
                if not (entry.isfile() or entry.isdir()):
                    die("Unexpected archive entry type: " + entry.name)
            archive.extractall(staging, filter="data")
        candidate = staging / "lichii"
        binary = candidate / "bin/lichii"
        if not binary.is_file() or not (binary.stat().st_mode & 0o111):
            die("Package executable missing or not executable")
        if sha(binary) != BINARY_SHA256:
            die("Packaged Lichii binary does not match verified Odin build")
        if RELEASE.is_symlink():
            die("Existing release directory is a symlink; will not follow it")
        if RELEASE.exists():
            if not (RELEASE / "bin/lichii").is_file() or sha(RELEASE / "bin/lichii") != sha(binary):
                die("Existing release directory differs. Will not overwrite it")
            print("PASS: Same release already installed")
        else:
            os.replace(candidate, RELEASE)
            print("PASS: Installed release into", RELEASE)
    if LINK.is_symlink() and LINK.exists():
        print("PRESERVED: Current active Lichii:", LINK.resolve())
        print("New release staged. Existing installation deliberately left active.")
        return
    # Check Toolbox's dynamic libraries without running the emulator itself.
    ldd = subprocess.run(["toolbox", "run", "--container", "lichii-debug", "ldd", str(RELEASE / "bin/lichii")],
                         capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    if ldd.returncode != 0 or "not found" in ldd.stdout or "not found" in ldd.stderr:
        print(ldd.stdout[-2500:]); print(ldd.stderr[-500:])
        die("Runtime dependencies missing; installed as inactive candidate, consult README")
    if LINK.is_symlink() and not LINK.exists():
        die("Existing active symlink is broken; manual recovery required")
    LINK.parent.mkdir(parents=True, exist_ok=True)
    LAUNCHER.parent.mkdir(parents=True, exist_ok=True)
    DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    TOOLS.mkdir(parents=True, exist_ok=True)
    launcher_in = RELEASE / "scripts/launch-odin.sh"
    if not launcher_in.is_file():
        die("Launch script missing from archive")
    if LAUNCHER.exists() or LAUNCHER.is_symlink():
        die("Launcher path already exists; leave it untouched")
    # First install only: copy script that calls Toolbox and the LSFG preflight.
    shutil.copy2(launcher_in, LAUNCHER)
    LAUNCHER.chmod(0o755)
    for name in ("steam-integration.py", "steam_artwork.py", "steam_artwork_manual.py", "steam_dashboard.py",
                 "steam_duplicate_manager.py", "steam_duplicate_apply.py", "steam_undo.py", "steam_library_tools.py"):
        src = RELEASE / "scripts" / name
        dst = TOOLS / name
        if src.is_file() and not (dst.exists() or dst.is_symlink()):
            shutil.copy2(src, dst)
    temp_link = LINK.with_name(".lichii-odin-nx2-install-pending")
    if temp_link.exists() or temp_link.is_symlink():
        die("Temporary activation path occupied")
    os.symlink(str(RELEASE / "bin/lichii"), temp_link)
    os.replace(temp_link, LINK)
    DESKTOP.write_text("[Desktop Entry]\nType=Application\nName=Lichii NX2 (Odin ARM64)\n"
                       f"Exec={LAUNCHER}\nIcon=applications-games\nTerminal=false\nCategories=Game;Emulator;\n")
    DESKTOP.chmod(0o755)
    # Best-effort clone of the matching public source for Steam UI helper commands.
    source_checkout = ROOT / "source"
    if not source_checkout.exists() and not source_checkout.is_symlink() and shutil.which("git"):
        clone = subprocess.run(["git", "clone", "--depth", "1", "--branch", TAG,
                                "https://github.com/" + REPO + ".git", str(source_checkout)],
                               stdin=subprocess.DEVNULL, capture_output=True, text=True)
        if clone.returncode == 0:
            print("PASS: Matching source helpers installed")
        else:
            print("WARNING: Could not clone source helpers; extra Steam menu actions may be unavailable")
    print("PASS: Fresh Lichii NX2 installed and launcher created")
    print("No ROMs, keys, firmware, Lossless.dll or game data were bundled or modified")
    print("Open your Games menu to launch Lichii. See README-ODIN-NX2.md for Steam menu prerequisites.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, urllib.error.URLError, subprocess.CalledProcessError) as error:
        die(str(error))

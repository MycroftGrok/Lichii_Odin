#!/usr/bin/env bash
# One-paste binary installer for AYN Odin / ArmadaOS. No root or source build.
# Existing working executable and source checkout are NEVER replaced.
set -euo pipefail

REPO="MycroftGrok/Lichii_Odin"
ROOT="$HOME/Applications/Lichii"
BIN="$ROOT/bin/lichii-odin"
LAUNCHER="$HOME/.local/bin/lichii-odin"
MENU="$HOME/.local/share/applications/lichii-odin.desktop"
ARCHIVE="lichii-odin-armadaos-aarch64.tar.gz"

die() { echo "ERROR: $*" >&2; exit 1; }

[[ "$(uname -m)" == aarch64 ]] || die "This release only supports ARM64 (aarch64)."
for command_name in python3 curl tar sha256sum; do
    command -v "$command_name" >/dev/null 2>&1 ||
        die "Missing dependency: $command_name"
done

echo "=== FIND LATEST ODIN ARM64 RELEASE ==="
# Only select releases published by this fork, with both our archive and hash manifest.
metadata="$(python3 - "$REPO" "$ARCHIVE" <<'PY'
import json, sys, urllib.request
repo, archive = sys.argv[1:]
url = f"https://api.github.com/repos/{repo}/releases?per_page=30"
request = urllib.request.Request(url, headers={
    "Accept": "application/vnd.github+json",
    "User-Agent": "Lichii-Odin-arm64-installer",
})
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        releases = json.load(response)
except Exception as error:
    sys.exit(f"Could not fetch GitHub releases: {error}")
prefix = f"https://github.com/{repo}/releases/download/"
for release in releases:
    if release.get("draft") or not release.get("tag_name", "").startswith("odin-armadaos-build-"):
        continue
    assets = {item["name"]: item["browser_download_url"]
              for item in release.get("assets", [])}
    if archive in assets and "SHA256SUMS" in assets:
        links = (assets[archive], assets["SHA256SUMS"])
        if all(link.startswith(prefix) for link in links):
            print("\n".join((release["tag_name"], *links)))
            break
else:
    sys.exit("No packaged Odin ARM64 release yet. Check the fork's Actions/Releases pages.")
PY
)" || die "Release discovery failed."

TAG="$(printf '%s\n' "$metadata" | sed -n '1p')"
ARCHIVE_URL="$(printf '%s\n' "$metadata" | sed -n '2p')"
HASH_URL="$(printf '%s\n' "$metadata" | sed -n '3p')"
[[ "$TAG" =~ ^odin-armadaos-build-[0-9]+$ ]] || die "Unexpected release tag"
echo "Selected: $TAG"

mkdir -p "$ROOT/releases" "$ROOT/bin" "$HOME/.local/bin" \
    "$HOME/.local/share/applications"
WORK="$(mktemp -d "$ROOT/releases/.download-XXXXXXXX")"
trap 'rm -rf -- "$WORK"' EXIT

echo "=== DOWNLOAD AND VERIFY PACKAGE ==="
curl -fL --retry 3 -o "$WORK/$ARCHIVE" "$ARCHIVE_URL"
curl -fL --retry 3 -o "$WORK/SHA256SUMS" "$HASH_URL"
expected="$(awk -v filename="$ARCHIVE" '$2 == filename { print $1 }' "$WORK/SHA256SUMS")"
[[ "$expected" =~ ^[a-fA-F0-9]{64}$ ]] || die "Invalid SHA256 manifest"
printf '%s  %s\n' "$expected" "$ARCHIVE" |
    (cd "$WORK" && sha256sum --check --status -) ||
    die "Archive checksum failed; no executable was installed."
echo "PASS: Official release checksum matches."

# Validate paths and symlinks before extraction to avoid tar path escapes.
python3 - "$WORK/$ARCHIVE" <<'PY'
import posixpath, sys, tarfile
with tarfile.open(sys.argv[1], "r:gz") as archive:
    for item in archive:
        name = item.name.removeprefix("./")
        clean = posixpath.normpath(name)
        if not (clean == "lichii" or clean.startswith("lichii/")):
            sys.exit(f"Unsafe archive member: {name!r}")
        if name.startswith("/") or ".." in name.split("/"):
            sys.exit(f"Unsafe archive member: {name!r}")
        if item.issym():
            target = posixpath.normpath(posixpath.join(posixpath.dirname(clean), item.linkname))
            if item.linkname.startswith("/") or not target.startswith("lichii/"):
                sys.exit(f"Unsafe symlink: {name!r} -> {item.linkname!r}")
        elif not (item.isfile() or item.isdir()):
            sys.exit(f"Unsupported archive member type: {name!r}")
PY

RELEASE="$ROOT/releases/$TAG"
if [[ ! -e "$RELEASE" ]]; then
    mkdir -p "$WORK/unpacked"
    tar -xzf "$WORK/$ARCHIVE" -C "$WORK/unpacked"
    [[ -x "$WORK/unpacked/lichii/usr/bin/lichii" ]] ||
        die "Release archive is missing an executable."
    [[ -e "$WORK/unpacked/lichii/usr/lib/libnxformat.so" ]] ||
        die "Release archive is missing libnxformat.so."
    mv -T -- "$WORK/unpacked" "$RELEASE"
    echo "Installed independent candidate: $RELEASE"
else
    [[ -x "$RELEASE/lichii/usr/bin/lichii" ]] ||
        die "Existing release directory is incomplete: $RELEASE"
    echo "Release already present: $RELEASE"
fi

# Detect an existing active version, including a broken symlink (never overwrite it).
FRESH=false
if [[ ! -e "$BIN" && ! -L "$BIN" ]]; then
    echo "=== FRESH INSTALL ==="
    ln -s -- "$RELEASE/lichii/lichii" "$BIN"
    FRESH=true

    # The packaged binary bundles Qt and launches directly on the ArmadaOS host.
    cat > "$LAUNCHER" <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail
BINARY="$HOME/Applications/Lichii/bin/lichii-odin"
[[ -x "$BINARY" ]] || { echo "Missing Lichii binary: $BINARY" >&2; exit 1; }
export QT_QPA_PLATFORM=wayland
ICD=/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json
if [[ -f "$ICD" ]]; then export VK_DRIVER_FILES="$ICD"; fi
exec "$BINARY" "$@"
LAUNCH
    chmod +x "$LAUNCHER"
else
    echo "=== PRESERVING EXISTING LICHII ==="
    echo "Stable emulator unchanged: $BIN"
    echo "Downloaded release is an UNACTIVATED candidate:"
    echo "$RELEASE/lichii/lichii"
    # On existing source installations, keep the known-working toolbox launcher.
    if [[ ! -x "$LAUNCHER" && -f "$ROOT/source/scripts/launch-odin.sh" ]]; then
        cp "$ROOT/source/scripts/launch-odin.sh" "$LAUNCHER"
        chmod +x "$LAUNCHER"
    fi
fi

[[ -x "$LAUNCHER" ]] ||
    die "No working launcher found. Stable executable was not modified."

# Prefer artwork from the source checkout, then from the release, then KDE's games icon.
ICON=applications-games
if [[ -f "$ROOT/source/dist/lichii.png" ]]; then
    ICON="$ROOT/source/dist/lichii.png"
else
    found_icon="$(find "$RELEASE/lichii/usr/share/icons" -type f -name '*.png' -print -quit 2>/dev/null || true)"
    [[ -z "$found_icon" ]] || ICON="$found_icon"
fi

echo "=== INSTALL KDE GAMES MENU AND DESKTOP SHORTCUT ==="
cat > "$MENU" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Lichii (Odin ARM64)
GenericName=Switch Emulator
Comment=Native Wayland Lichii for ArmadaOS
Exec=$LAUNCHER
Icon=$ICON
Terminal=false
Categories=Game;Emulator;
Keywords=Nintendo;Switch;Lichii;Odin;
StartupNotify=true
DESKTOP
chmod +x "$MENU"

DESKTOP_DIR="$HOME/Desktop"
if command -v xdg-user-dir >/dev/null 2>&1; then
    DETECTED="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
    if [[ -n "$DETECTED" && "$DETECTED" != "$HOME" ]]; then DESKTOP_DIR="$DETECTED"; fi
fi
mkdir -p "$DESKTOP_DIR"
cp "$MENU" "$DESKTOP_DIR/lichii-odin.desktop"
chmod +x "$DESKTOP_DIR/lichii-odin.desktop"
if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 >/dev/null 2>&1 || true
fi


# Steam integration can run directly from the Games menu or Lichii's Steam menu.
# Only add its own wrapper and helper; never swap an already-working emulator.
echo "=== INSTALL STEAM INTEGRATION ==="
mkdir -p "$HOME/.local/share/lichii/tools" "$HOME/.local/bin"
HELPER="$HOME/.local/share/lichii/tools/steam-integration.py"
if [[ -f "$ROOT/source/scripts/steam-integration.py" ]]; then
    cp -p "$ROOT/source/scripts/steam-integration.py" "$HELPER"
else
    curl -fLsS --retry 3 \
      "https://raw.githubusercontent.com/MycroftGrok/Lichii_Odin/odin-armadaos/scripts/steam-integration.py" \
      -o "$HELPER"
fi
ART_HELPER="$HOME/.local/share/lichii/tools/steam_artwork.py"
if [[ -f "$ROOT/source/scripts/steam_artwork.py" ]]; then
    cp -p "$ROOT/source/scripts/steam_artwork.py" "$ART_HELPER"
else
    curl -fLsS --retry 3 \
      "https://raw.githubusercontent.com/MycroftGrok/Lichii_Odin/odin-armadaos/scripts/steam_artwork.py" \
      -o "$ART_HELPER"
fi
python3 -m py_compile "$HELPER" "$ART_HELPER"
cat > "$HOME/.local/bin/lichii-steam-game" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 || ! -f "$1" ]]; then
    echo "Expected one existing ROM file path" >&2
    exit 1
fi
exec "$HOME/.local/bin/lichii-odin" -f -g "$1"
WRAPPER
chmod +x "$HOME/.local/bin/lichii-steam-game"

STEAM_MENU="$HOME/.local/share/applications/lichii-steam-integration.desktop"
cat > "$STEAM_MENU" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Steam Integration
GenericName=Import Lichii ROMs into Steam
Comment=Import Switch and Switch 2 games into Steam collections
Exec=konsole --hold -e /usr/bin/python3 $HOME/.local/share/lichii/tools/steam-integration.py --mode all
Icon=steam
Terminal=false
Categories=Game;Utility;
Keywords=Steam;Lichii;Switch;Switch2;
DESKTOP
chmod +x "$STEAM_MENU"
echo "PASS: Games menu → Steam Integration"

echo
echo "PASS: Games menu shortcut: $MENU"
echo "PASS: Desktop shortcut: $DESKTOP_DIR/lichii-odin.desktop"
if [[ "$FRESH" == true ]]; then
    echo "PASS: Fresh installation completed. Launch Lichii from Games or your desktop."
else
    echo "PASS: Existing stable Lichii preserved and shortcuts refreshed."
    echo "The experimental release was downloaded separately, NOT made active."
fi
echo "No game data, save files, original source or backups were deleted."

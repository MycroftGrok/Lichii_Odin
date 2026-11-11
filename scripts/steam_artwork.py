#!/usr/bin/env python3
"""SteamGridDB artwork for Lichii-managed non-Steam ROM shortcuts.

Optional: no API key means no scraping. The key lives only on the local device.
Uses standard-library HTTPS, exact title matching, and never overwrites artwork.
"""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

KEY_FILE = Path.home() / ".config/lichii/steamgriddb-api-key"
API = "https://www.steamgriddb.com/api/v2"
MAX_IMAGE = 15 * 1024 * 1024
ARTWORK_TYPES = (
    ("portrait cover", "grids", "600x900", "p"),
    ("landscape cover", "grids", "920x430,460x215", ""),
    ("hero background", "heroes", None, "_hero"),
    ("transparent logo", "logos", None, "_logo"),
    ("icon", "icons", None, "_icon"),
)


def token() -> str | None:
    key = os.environ.get("STEAMGRIDDB_API_KEY", "").strip()
    if key:
        return key
    if not KEY_FILE.is_file() or KEY_FILE.is_symlink():
        return None
    key = KEY_FILE.read_text(encoding="utf-8").strip()
    return key or None


def configure_key() -> bool:
    print("SteamGridDB: https://www.steamgriddb.com/profile/preferences/api")
    print("Create a free API key there, then paste it below. Input will be hidden.")
    value = getpass.getpass("SteamGridDB API key: ").strip()
    if not value:
        print("Canceled. No key saved.")
        return False
    if any(ch.isspace() for ch in value) or len(value) > 1024 or len(value) < 12:
        raise ValueError("Invalid API key shape. No changes made.")
    if KEY_FILE.is_symlink():
        raise ValueError("Refusing to write API key through a symbolic link.")
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.parent.chmod(0o700)
    fd = os.open(KEY_FILE, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(value + "\n")
    KEY_FILE.chmod(0o600)
    print("API key saved locally (permissions 0600):", KEY_FILE)
    return True


def normalized(title: str) -> str:
    cleaned = re.sub(r"[\[(](?:USA|EUR|EU|JPN|JAP|World|Switch ?2|Switch|Rev ?\d+|v\d+|0100[A-Fa-f0-9]+)[\])]", " ", title, flags=re.I)
    cleaned = re.sub(r"(?i)(?:\s*[-_]\s*)?(?:\(\d{4}\)|\[update\]|\[dlc\])$", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9]+", "", cleaned.casefold())
    return cleaned


def search_title(title: str) -> str:
    cleaned = re.sub(r"[\[(](?:USA|EUR|EU|JPN|JAP|World|Switch ?2|Switch|Rev ?\d+|v\d+|0100[A-Fa-f0-9]+)[\])]", " ", title, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_")
    return cleaned or title


def request_json(path: str, key: str) -> list:
    url = API + path
    req = Request(url, headers={
        "Authorization": "Bearer " + key,
        "Accept": "application/json",
        "User-Agent": "Lichii-Odin-Steam-Integration/1.0",
    })
    try:
        with urlopen(req, timeout=25) as response:
            payload = response.read(2 * 1024 * 1024 + 1)
        if len(payload) > 2 * 1024 * 1024:
            raise RuntimeError("SteamGridDB returned too much data.")
        body = json.loads(payload.decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError("SteamGridDB rejected the API key. Reconfigure it.") from exc
        raise RuntimeError(f"SteamGridDB HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"SteamGridDB connection failed: {exc}") from exc
    if not isinstance(body, dict) or not body.get("success"):
        raise RuntimeError("SteamGridDB returned an unsuccessful response.")
    entries = body.get("data", [])
    return entries if isinstance(entries, list) else []


def lookup_game_id(title: str, key: str) -> int | None:
    results = request_json("/search/autocomplete/" + quote(title, safe=""), key)
    expected = normalized(title)
    matches = [x for x in results
               if isinstance(x, dict)
               and normalized(str(x.get("name", ""))) == expected
               and isinstance(x.get("id"), int)]
    if not matches:
        print(f"  No unambiguous exact SteamGridDB match: {title}")
        return None
    # Same title across versions/platforms: do not guess which art belongs to the ROM.
    if len(matches) > 1:
        print(f"  Ambiguous SteamGridDB matches ({len(matches)}): {title}")
        return None
    return matches[0]["id"]


def image_extension(blob: bytes, kind: str) -> str | None:
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if blob.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if kind == "icon" and blob.startswith(b"\x00\x00\x01\x00"):
        return ".ico"
    return None


def load_image(url: str, kind: str) -> tuple[bytes, str]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not re.fullmatch(r"cdn\d*\.steamgriddb\.com", parsed.hostname or ""):
        raise ValueError("Artwork URL is not an approved SteamGridDB CDN host.")
    req = Request(url, headers={"User-Agent": "Lichii-Odin-Steam-Integration/1.0"})
    with urlopen(req, timeout=30) as response:
        final = urlsplit(response.geturl())
        if final.scheme != "https" or not re.fullmatch(r"cdn\d*\.steamgriddb\.com", final.hostname or ""):
            raise ValueError("Artwork download redirected outside SteamGridDB CDN.")
        blob = response.read(MAX_IMAGE + 1)
    if len(blob) > MAX_IMAGE:
        raise ValueError("Artwork too large.")
    ext = image_extension(blob, kind)
    if not ext:
        raise ValueError("Unsupported artwork format (PNG/JPEG or ICO icon only).")
    return blob, ext


def existing_art(grid_dir: Path, appid: int, suffix: str) -> bool:
    return any((grid_dir / f"{appid}{suffix}{ext}").is_file()
               for ext in (".png", ".jpg", ".jpeg", ".ico", ".webp"))


def save_art(grid_dir: Path, filename: str, data: bytes) -> None:
    grid_dir.mkdir(parents=True, exist_ok=True)
    target = grid_dir / filename
    if target.exists():
        return
    with tempfile.NamedTemporaryFile(dir=grid_dir, prefix=".lichii-art-", delete=False) as stream:
        temp = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        # No overwrites, including Steam or user-customized artwork.
        if not target.exists():
            os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def scrape_one(grid_dir: Path, appid: int, title: str, key: str) -> tuple[int, int]:
    missing = [(label, endpoint, dims, suffix)
               for label, endpoint, dims, suffix in ARTWORK_TYPES
               if not existing_art(grid_dir, appid, suffix)]
    if not missing:
        return 0, 0
    query = search_title(title)
    game_id = lookup_game_id(query, key)
    if game_id is None:
        return 0, len(missing)
    installed = 0
    for label, endpoint, dims, suffix in missing:
        try:
            route = f"/{endpoint}/game/{game_id}"
            query = ("?dimensions=" + quote(dims, safe=",")) if dims else ""
            assets = request_json(route + query, key)
            for row in assets:
                if not isinstance(row, dict):
                    continue
                if row.get("type") == "animated":
                    continue
                url = row.get("url")
                if not isinstance(url, str):
                    continue
                try:
                    blob, ext = load_image(url, "icon" if endpoint == "icons" else endpoint)
                    save_art(grid_dir, f"{appid}{suffix}{ext}", blob)
                    installed += 1
                    print(f"  {label}: installed")
                    break
                except (OSError, ValueError, URLError, TimeoutError) as exc:
                    print(f"  {label}: skipped candidate ({exc})")
            else:
                print(f"  {label}: not available")
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"  {label}: unavailable ({exc})")
    return installed, len(missing) - installed


def apply_artwork(grid_dir: Path, apps: list[tuple[int, str]], *, dry_run=False) -> None:
    if not apps:
        return
    key = token()
    if not key:
        print("Artwork skipped: no SteamGridDB API key configured.")
        print("Configure once in Konsole:")
        print('python3 "$HOME/.local/share/lichii/tools/steam_artwork.py" --configure')
        return
    printed = set()
    total, missing = 0, 0
    for appid, title in apps:
        if appid in printed:
            continue
        printed.add(appid)
        if dry_run:
            print(f"ARTWORK PREVIEW: {title} [Steam ID {appid}]")
            continue
        if not grid_dir.exists() and len(printed) == 1:
            grid_dir.mkdir(parents=True, exist_ok=True)
        print(f"ARTWORK: {title}")
        try:
            got, skipped = scrape_one(grid_dir, appid, title, key)
            total += got
            missing += skipped
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"  skipped: {exc}")
            missing += 5
    print(f"Artwork summary: {total} installed; {missing} missing/unmatched assets.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SteamGridDB artwork key configuration")
    parser.add_argument("--configure", action="store_true",
                        help="Securely save your personal SteamGridDB key")
    args = parser.parse_args()
    if args.configure:
        try:
            configure_key()
        except (EOFError, KeyboardInterrupt):
            print("\nCanceled; no API key changed.")
        except (OSError, ValueError) as error:
            print(f"ERROR: {error}", file=__import__("sys").stderr)
            raise SystemExit(1)
    else:
        parser.print_help()

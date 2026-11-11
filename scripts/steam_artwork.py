#!/usr/bin/env python3
"""SteamGridDB artwork for Lichii-managed non-Steam ROM shortcuts.

Optional: no API key means no scraping. The key lives only on the local device.
Uses standard-library HTTPS, exact title matching, and never overwrites artwork.
"""
from __future__ import annotations

import getpass
import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

KEY_FILE = Path.home() / ".config/lichii/steamgriddb-api-key"
MATCH_FILE = Path.home() / ".config/lichii/steamgriddb-artwork-matches.json"
API = "https://www.steamgriddb.com/api/v2"
MAX_IMAGE = 15 * 1024 * 1024

# SteamGridDB does not index Nintendo Title IDs. These are verified mappings
# from a Nintendo game title ID to a distinct SteamGridDB game listing.
# Only add known, reviewed mappings. Unknown IDs are never guessed.
KNOWN_TITLE_ID_TO_SGDB = {
    "0400486024DEC000": 5532594,  # Zelda: Ocarina of Time (Switch 2, 2026)
}


def title_id_from_rom(rom_path: str | Path) -> str | None:
    """Extract Nintendo's 16-hex title ID only when explicitly present in a ROM name."""
    stem = Path(rom_path).stem
    match = re.search(r"(?i)\[([0-9a-f]{16})\]", stem)
    return match.group(1).upper() if match else None
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


def exact_game_matches(title: str, key: str) -> list[dict]:
    """All distinct SteamGridDB IDs with the exact normalized game title."""
    results = request_json("/search/autocomplete/" + quote(title, safe=""), key)
    expected = normalized(title)
    matches = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        game_id = item.get("id")
        name = item.get("name")
        if (type(game_id) is not int or game_id <= 0 or
                not isinstance(name, str) or normalized(name) != expected):
            continue
        date = item.get("release_date")
        year = None
        if type(date) is int and 0 < date < 32503680000:
            year = datetime.datetime.fromtimestamp(date, datetime.timezone.utc).year
        matches[game_id] = {"id": game_id, "name": name, "year": year}
    return sorted(matches.values(), key=lambda m: (m["year"] or 9999, m["id"]))


def chosen_game_matches() -> dict:
    if MATCH_FILE.is_symlink():
        raise RuntimeError("Refusing symbolic link for SteamGridDB match preferences")
    if not MATCH_FILE.is_file():
        return {}
    if MATCH_FILE.stat().st_size > 128 * 1024:
        raise RuntimeError("SteamGridDB artwork preferences are unexpectedly large")
    data = json.loads(MATCH_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("SteamGridDB artwork preferences must be a JSON object")
    return data


def set_game_match(appid: int, title: str, game_id: int, key: str,
                   title_id: str | None = None) -> None:
    """Persist a user-selected candidate, after validating an exact match."""
    if not 0 < appid < (1 << 32) or game_id <= 0:
        raise ValueError("Invalid Steam shortcut or SteamGridDB ID")
    candidates = exact_game_matches(search_title(title), key)
    if game_id not in {c["id"] for c in candidates}:
        raise ValueError("Selected SteamGridDB game is not an exact title match")
    selected = chosen_game_matches()
    selected[str(appid)] = {"game_id": game_id, "title": title}
    if title_id is not None and re.fullmatch(r"[0-9A-F]{16}", title_id):
        selected["title-id:" + title_id] = {"game_id": game_id, "title": title}
    if MATCH_FILE.parent.is_symlink():
        raise ValueError("Refusing symlink for Lichii configuration folder")
    MATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
            dir=MATCH_FILE.parent, prefix=".steamgriddb-match-", delete=False,
            mode="w", encoding="utf-8") as stream:
        tmp = Path(stream.name)
        os.chmod(stream.fileno(), 0o600)
        json.dump(selected, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        if MATCH_FILE.is_symlink():
            raise ValueError("Refusing symbolic link for SteamGridDB preferences")
        os.replace(tmp, MATCH_FILE)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"Saved SteamGridDB artwork match: {title} -> game ID {game_id}")


def lookup_game_id(title: str, key: str, appid: int | None = None,
                   title_id: str | None = None) -> int | None:
    matches = exact_game_matches(title, key)
    if not matches:
        print(f"  No exact SteamGridDB match: {title}")
        return None
    valid_ids = {row["id"] for row in matches}
    if title_id is not None and re.fullmatch(r"[0-9A-F]{16}", title_id):
        verified = KNOWN_TITLE_ID_TO_SGDB.get(title_id)
        if verified in valid_ids:
            print(f"  Nintendo Title ID {title_id}: verified SteamGridDB game {verified}")
            return verified
        choice = chosen_game_matches().get("title-id:" + title_id)
        if (isinstance(choice, dict) and choice.get("game_id") in valid_ids and
                normalized(str(choice.get("title", ""))) == normalized(title)):
            print(f"  Nintendo Title ID {title_id}: saved game {choice['game_id']}")
            return choice["game_id"]
    if len(matches) == 1:
        return matches[0]["id"]
    if appid is not None:
        preferred = chosen_game_matches().get(str(appid))
        if (isinstance(preferred, dict) and preferred.get("title") == title and
                preferred.get("game_id") in valid_ids):
            print(f"  Using saved SteamGridDB match ID {preferred['game_id']}")
            return preferred["game_id"]
    print(f"  Ambiguous SteamGridDB matches ({len(matches)}): {title}")
    for candidate in matches:
        year = f" ({candidate['year']})" if candidate["year"] else ""
        print(f"    {candidate['id']}: {candidate['name']}{year}"
              f" — https://www.steamgriddb.com/game/{candidate['id']}")
    print("  Choose a matching SteamGridDB game in Lichii's Steam menu.")
    return None


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


def scrape_one(grid_dir: Path, appid: int, title: str, key: str,
               title_id: str | None = None) -> tuple[int, int]:
    missing = [(label, endpoint, dims, suffix)
               for label, endpoint, dims, suffix in ARTWORK_TYPES
               if not existing_art(grid_dir, appid, suffix)]
    if not missing:
        return 0, 0
    query = search_title(title)
    game_id = lookup_game_id(query, key, appid=appid, title_id=title_id)
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


def apply_artwork(grid_dir: Path, apps: list[tuple[int, str]], *, dry_run=False,
                  title_ids: dict[int, str] | None = None) -> None:
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
            got, skipped = scrape_one(grid_dir, appid, title, key,
                                      title_id=(title_ids or {}).get(appid))
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

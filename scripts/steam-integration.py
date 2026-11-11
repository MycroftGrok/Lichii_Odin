#!/usr/bin/env python3
"""Steam Integration for Lichii: Switch / Switch 2, idempotent and reversible.

Works with modern Steam cloud-storage collections and binary shortcuts.vdf.
Only deletes shortcuts owned by this integration. Steam must be fully closed.
Never removes ROMs, Lichii configuration, or other Steam shortcuts.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib

HOME = Path.home()
SCRIPT = HOME / ".local/bin/lichii-steam-game"
LAUNCHER = HOME / ".local/bin/lichii-odin"
EXTS = {".nsp", ".xci", ".nsz", ".xcz", ".nup", ".nro"}
BACKUPS = HOME / ".local/share/lichii/steam-integration-backups"
PROFILES = [
    HOME / ".config/lichii/qt-config.ini",
    HOME / ".local/share/lichii/config/qt-config.ini",
    HOME / ".config/eden/qt-config.ini",
    HOME / ".local/share/eden/config/qt-config.ini",
]
ROOTS = [
    HOME / "Applications/Lichii/roms", HOME / "Applications/Lichii/ROMs",
    HOME / "Applications/Lichii/games",
    HOME / "Games/Switch", HOME / "Games/Switch 2", HOME / "Games/Switch2",
    HOME / "ROMs/Switch", HOME / "ROMs/Switch 2", HOME / "ROMs/Switch2",
    HOME / "Roms/Switch", HOME / "Roms/Switch 2",
]
STEAM_ROOTS = [
    HOME / ".local/share/Steam",
    HOME / ".steam/root",
    HOME / ".steam/steam",
    HOME / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
]
CATEGORIES = ("Switch", "Switch 2")


def abort(message: str):
    raise RuntimeError(message)


def read_cstring(blob: bytes, start: int) -> tuple[str, int]:
    end = blob.find(b"\0", start)
    if end < 0:
        abort("Corrupt Steam shortcuts.vdf (unterminated string)")
    return blob[start:end].decode("utf-8", errors="replace"), end + 1


def parse_object(blob: bytes, start: int):
    """Keep original byte spans, so unrecognized but valid fields aren't rewritten."""
    fields, pos = {}, start
    while pos < len(blob):
        record_start = pos
        tag = blob[pos]
        pos += 1
        if tag == 8:
            return fields, pos, record_start
        key, pos = read_cstring(blob, pos)
        if tag == 0:
            value, pos, _ = parse_object(blob, pos)
        elif tag == 1:
            value, pos = read_cstring(blob, pos)
        elif tag in (2, 3, 4, 6):
            if pos + 4 > len(blob):
                abort("Corrupt Steam shortcuts.vdf (truncated field)")
            value = struct.unpack_from("<i", blob, pos)[0] if tag == 2 else None
            pos += 4
        elif tag in (7, 9, 10):
            if pos + 8 > len(blob):
                abort("Unsupported truncated 64-bit field in shortcuts.vdf")
            value = None
            pos += 8
        else:
            abort(f"Unknown Steam shortcuts.vdf field type {tag}; refusing to modify")
        fields[key] = (value, record_start, pos)
    abort("Corrupt Steam shortcuts.vdf (unterminated object)")


def read_shortcuts(blob: bytes):
    if not blob:
        blob = b"\x00shortcuts\x00\x08\x08"
    if not blob.startswith(b"\x00shortcuts\x00"):
        abort("Unrecognized Steam shortcuts.vdf root")
    fields, end, close_at = parse_object(blob, len(b"\x00shortcuts\x00"))
    if blob[end:] not in (b"", b"\x08"):
        abort("Unrecognized trailing Steam shortcuts.vdf data")
    entries = []
    for key, (obj, start, stop) in fields.items():
        if key.isdecimal() and isinstance(obj, dict):
            def get(name, default=""):
                return next((val for k, (val, _, _) in obj.items()
                             if k.casefold() == name.casefold()), default)
            entries.append({"key": key, "start": start, "stop": stop,
                            "appid": get("appid"), "name": get("AppName"),
                            "exe": str(get("Exe")), "options": str(get("LaunchOptions"))})
    index = max((int(k) for k in fields if k.isdecimal()), default=-1) + 1
    return blob, entries, close_at, index


def vstring(key: str, value: str) -> bytes:
    return b"\x01" + key.encode() + b"\0" + value.encode("utf-8") + b"\0"


def vint(key: str, value: int) -> bytes:
    return b"\x02" + key.encode() + b"\0" + struct.pack("<i", value)


def make_shortcut(index: int, appid: int, title: str, rom: Path) -> bytes:
    signed = appid - (1 << 32) if appid >= (1 << 31) else appid
    exe = '"' + str(SCRIPT) + '"'
    # Steam passes LaunchOptions through a shell. Use POSIX single-quote escaping
    # so dollar signs, backticks and command substitutions in ROM paths stay literal.
    opts = shlex.quote(str(rom))
    return (b"\x00" + str(index).encode() + b"\0"
            + vint("appid", signed)
            + vstring("AppName", title)
            + vstring("Exe", exe)
            + vstring("StartDir", '"' + str(SCRIPT.parent) + '"')
            + vstring("icon", "")
            + vstring("ShortcutPath", "")
            + vstring("LaunchOptions", opts)
            + vint("IsHidden", 0)
            + vint("AllowDesktopConfig", 1)
            + vint("AllowOverlay", 1)
            + vint("OpenVR", 0)
            + vint("Devkit", 0)
            + vstring("DevkitGameID", "")
            + vint("LastPlayTime", 0)
            + vstring("FlatpakAppID", "")
            + b"\x00tags\x00\x08\x08")


def owned(entry: dict) -> bool:
    exe = entry["exe"].strip('"')
    return exe == str(SCRIPT) and get_path(entry) is not None


def get_path(entry: dict) -> str | None:
    # Recognize our wrapper and pre-existing Lichii shortcuts using -g.
    # Never guess a ROM from unrelated Steam games.
    import shlex
    options = entry["options"].strip()
    try:
        args = shlex.split(options)
    except ValueError:
        return None
    possible = None
    if len(args) == 1:
        possible = args[0]
    elif "-g" in args and args.index("-g") + 1 < len(args):
        possible = args[args.index("-g") + 1]
    elif "--game" in args and args.index("--game") + 1 < len(args):
        possible = args[args.index("--game") + 1]
    if possible:
        path = Path(possible).expanduser()
        if path.is_absolute() and path.suffix.casefold() in EXTS:
            return str(path.resolve())
    return None


def steam_running() -> bool:
    try:
        ps = subprocess.check_output(["ps", "-eo", "comm="], text=True)
    except (OSError, subprocess.CalledProcessError):
        abort("Cannot check running processes; Steam files left unchanged")
    return any(n.strip() in ("steam", "steamwebhelper", "steam-runtime-launcher")
               for n in ps.splitlines())


def discover_steam():
    matches = {str(p.resolve()): p.resolve() for p in STEAM_ROOTS
               if (p / "userdata").is_dir()}
    if len(matches) != 1:
        abort("Need exactly one Steam installation with userdata; found "
              + str(len(matches)) + ". Use the native Steam installation/profile.")
    steam = next(iter(matches.values()))
    users = [p for p in (steam / "userdata").iterdir()
             if p.is_dir() and p.name.isdecimal() and (p / "config").is_dir()]
    if len(users) != 1:
        abort("Need exactly one Steam userdata account; found "
              + str(len(users)) + ". Sign in to the intended Steam account first.")
    user = users[0]
    shortcuts = user / "config/shortcuts.vdf"
    cloud = user / "config/cloudstorage"
    # Current Steam format: namespace 1 stores user-collections.
    collections = cloud / "cloud-storage-namespace-1.json"
    namespaces = cloud / "cloud-storage-namespaces.json"
    if not (collections.is_file() and namespaces.is_file()):
        abort("Steam collection files missing; sign in to Steam and create a "
              "collection once, then exit Steam completely.")
    return user, shortcuts, collections, namespaces


def usable_game_directories(configured: Path) -> set[Path]:
    """Resolve configured library folders, including ArmadaOS's /media alias.

    ArmadaOS mounts removable cards under /run/media/<user>/<label>, while
    previous Lichii configs can contain /media/<user>/<label>. Never change
    the config or create mounts; only scan an alias if it really exists.
    """
    candidates = [configured]
    parts = configured.parts
    if len(parts) > 2 and parts[0] == "/" and parts[1] == "media":
        candidates.append(Path("/run") / configured.relative_to("/"))
    elif len(parts) > 3 and parts[:3] == ("/", "run", "media"):
        candidates.append(Path("/") / Path(*parts[2:]))
    valid = set()
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        valid.add(candidate.resolve())
        # A library configured at Switch 2 should also pick up a sibling
        # Switch 1 directory on the same card (and vice versa).
        if candidate.name.casefold().replace(" ", "") in ("switch", "switch1", "switch2"):
            for sibling in ("Switch", "Switch 1", "Switch 2", "Switch2"):
                other = candidate.parent / sibling
                if other.is_dir():
                    valid.add(other.resolve())
    return valid


def scan_roots(extra):
    roots = {p.resolve() for p in ROOTS if p.is_dir()}
    # QSettings stores the path under Paths\gamedirs\N\path, not just
    # gamedirs\N\path. Config files may also use forward slashes.
    game_dir_pattern = re.compile(
        r"^\s*(?:Paths[\\/])?gamedirs[\\/]\d+[\\/]path\s*=\s*(.*?)\s*$",
        re.I,
    )
    recent_files_pattern = re.compile(
        r"^\s*(?:Paths[\\/])?recentFiles\s*=\s*(.*?)\s*$",
        re.I,
    )
    for config in PROFILES:
        if not config.is_file():
            continue
        for line in config.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            found = game_dir_pattern.match(line)
            if found:
                raw = found.group(1).strip().strip('"')
                if raw and raw not in ("SDMC", "UserNAND", "SysNAND"):
                    path = Path(os.path.expandvars(raw)).expanduser()
                    roots.update(usable_game_directories(path))
            else:
                recent = recent_files_pattern.match(line)
                if recent:
                    for raw in recent.group(1).split(","):
                        path = Path(os.path.expandvars(raw.strip().strip('"'))).expanduser()
                        if path.suffix.casefold() in EXTS:
                            roots.update(usable_game_directories(path.parent))
    for arg in extra:
        path = Path(arg).expanduser()
        directories = usable_game_directories(path)
        if not directories:
            abort(f"ROM directory not found: {path}")
        roots.update(directories)
    return sorted(roots)

def roms_in(roots):
    roms = {}
    for root in roots:
        for base, directories, filenames in os.walk(root, followlinks=False):
            directories[:] = [d for d in directories if not d.startswith(".")]
            for filename in filenames:
                path = Path(base) / filename
                if path.suffix.casefold() in EXTS and path.is_file():
                    roms[str(path.resolve())] = path.resolve()
    return [roms[key] for key in sorted(roms)]


def classify(rom: Path, selected: str) -> str | None:
    # Folder names are authoritative. NSP/XCI alone cannot reveal generation.
    for component in reversed(rom.parent.parts):
        slug = re.sub(r"[\s_.-]+", "", component).casefold()
        if slug in ("switch2", "nintendoswitch2", "nx2"):
            return "Switch 2"
        if slug in ("switch", "switch1", "nintendoswitch", "nsw"):
            return "Switch"
    if rom.suffix.casefold() == ".nup":
        return "Switch 2"
    return {"switch": "Switch", "switch2": "Switch 2"}.get(selected)


def non_game_package_reason(rom: Path) -> str | None:
    """Conservatively filter obvious updates/DLC from Steam's playable game list.

    Filename patterns are not a substitute for reading Switch content metadata.
    Only filter explicitly named add-on packages or add-on directories.
    """
    addon_dirs = {"dlc", "downloadablecontent", "updates", "update", "patches", "patch"}
    for parent in rom.parents:
        if re.sub(r"[\s_.-]+", "", parent.name).casefold() in addon_dirs:
            return "DLC/update directory"
    name = rom.stem
    if re.search(r"(?<![a-z0-9])(?:dlc|update|patch|unlocker)(?![a-z0-9])",
                 name, flags=re.I):
        return "DLC/update package"
    return None


def parse_collections(cloud: Path, namespaces: Path):
    data = json.loads(cloud.read_text(encoding="utf-8"))
    ns = json.loads(namespaces.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not isinstance(ns, list):
        abort("Unsupported Steam collections JSON format")
    collection_map = {}
    for index, entry in enumerate(data):
        if not isinstance(entry, list) or len(entry) != 2:
            abort("Unrecognized Steam cloudstorage entry")
        key, value = entry
        if (isinstance(key, str) and key.startswith("user-collections.")
                and isinstance(value, dict) and not value.get("is_deleted")
                and isinstance(value.get("value"), str)):
            doc = json.loads(value["value"])
            if isinstance(doc, dict) and isinstance(doc.get("name"), str):
                collection_map[doc["name"].casefold()] = (index, doc)
    versions = [int(x[1]) for x in ns if isinstance(x, list) and len(x) == 2
                and str(x[0]) == "1" and str(x[1]).isdigit()]
    if not versions:
        abort("Cannot determine Steam collections namespace version")
    high = max(versions + [int(e[1].get("version", "0")) for e in data
                           if isinstance(e[1], dict)
                           and str(e[1].get("version", "0")).isdigit()])
    return data, ns, collection_map, high


def update_collection(data, lookup, group, add_ids=(), remove_ids=(), version=0):
    item = lookup.get(group.casefold())
    if item:
        idx, doc = item
        if "filterSpec" in doc:
            abort(f"'{group}' is a dynamic collection; cannot edit safely")
        key = data[idx][0]
    else:
        key = "user-collections.lichii-" + group.casefold().replace(" ", "-")
        if any(row[0] == key for row in data):
            abort(f"Steam has deleted/duplicate collection key {key}; cannot recreate safely")
        doc = {"id": key.split(".")[1], "name": group, "added": [], "removed": []}
        idx = None
    added, removed = doc.get("added", []), doc.get("removed", [])
    if not isinstance(added, list) or not isinstance(removed, list):
        abort(f"Unsupported Steam collection membership in '{group}'")
    new_added = [x for x in added if x not in remove_ids]
    new_added.extend(x for x in add_ids if x not in new_added)
    new_removed = [x for x in removed if x not in add_ids and x not in remove_ids]
    if idx is not None and new_added == added and new_removed == removed:
        return False
    doc["added"], doc["removed"] = new_added, new_removed
    entry = [key, {
        "key": key, "timestamp": int(time.time()), "version": str(version),
        "value": json.dumps(doc, ensure_ascii=False, separators=(",", ":")),
        "conflictResolutionMethod": "custom", "strMethodId": "union-collections",
    }]
    if idx is None:
        idx = len(data)
        data.append(entry)
    else:
        original = data[idx][1]
        original.update(entry[1])
    lookup[group.casefold()] = (idx, doc)
    return True


def atomic_write(path: Path, content: bytes):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".lichii-", delete=False) as out:
        tmp = Path(out.name)
        out.write(content)
        out.flush()
        os.fsync(out.fileno())
    try:
        if path.exists():
            tmp.chmod(path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def get_artwork_module():
    # Load sibling module from source or installed tools, including unit-test imports.
    helper = Path(__file__).with_name("steam_artwork.py")
    if not helper.is_file():
        abort(f"Artwork module not installed: {helper}. Re-run install-launcher.sh.")
    spec = importlib.util.spec_from_file_location("lichii_steam_artwork", helper)
    if spec is None or spec.loader is None:
        abort(f"Cannot load artwork module: {helper}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def set_shortcut_icons(user: Path) -> None:
    """Fill blank icon fields only on Lichii-owned shortcuts, from downloaded icon art.

    Writing <appid>_icon.png to Steam's grid folder may not be enough to set the
    shortcut icon itself. Respect any custom icon the user already configured.
    """
    shortcuts = user / "config/shortcuts.vdf"
    if not shortcuts.is_file():
        return
    old = shortcuts.read_bytes()
    _, entries, _, _ = read_shortcuts(old)
    grid = user / "config/grid"
    changes = []
    for entry in entries:
        if not owned(entry) or not isinstance(entry["appid"], int):
            continue
        appid = entry["appid"] & 0xffffffff
        icon = next((grid / f"{appid}_icon{ext}" for ext in (".png", ".ico", ".jpg")
                     if (grid / f"{appid}_icon{ext}").is_file()), None)
        if icon is None:
            continue
        # Only update an existing *blank* icon field; don't replace user art.
        field_tag = b"\x01icon\x00"
        offset = old.find(field_tag, entry["start"], entry["stop"])
        if offset < 0:
            continue
        value_start = offset + len(field_tag)
        value_end = old.find(b"\x00", value_start, entry["stop"])
        if value_end != value_start:
            continue
        changes.append((value_start, str(icon).encode("utf-8")))
    if not changes:
        return
    modified = old
    for pos, value in sorted(changes, key=lambda pair: pair[0], reverse=True):
        modified = modified[:pos] + value + modified[pos:]
    if steam_running():
        abort("Steam started during icon update. Close Steam and retry.")
    if shortcuts.read_bytes() != old:
        abort("Steam shortcuts changed during icon update. Nothing was written.")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = BACKUPS / stamp
    target.mkdir(parents=True, exist_ok=False)
    (target / "shortcuts.vdf").write_bytes(old)
    atomic_write(shortcuts, modified)
    print(f"Updated {len(changes)} Steam shortcut icon paths; backup: {target}")


def scrape_apps(user: Path, apps: list[tuple[int, str]], args) -> None:
    if args.no_artwork:
        print("Artwork skipped (--no-artwork).")
        return
    get_artwork_module().apply_artwork(
        user / "config/grid", apps, dry_run=args.dry_run)
    if not args.dry_run:
        set_shortcut_icons(user)


def do_import(args):
    if steam_running():
        abort("Quit Steam completely before using Steam Integration. "
              "Steam overwrites shortcuts while running.")
    if not (LAUNCHER.is_file() and SCRIPT.is_file()):
        abort("Lichii Steam launcher missing. Run scripts/install-launcher.sh first.")
    user, shortcuts, cloud, namespaces = discover_steam()
    original_vdf = shortcuts.read_bytes() if shortcuts.is_file() else b"\x00shortcuts\x00\x08\x08"
    original_cloud = cloud.read_bytes()
    original_ns = namespaces.read_bytes()
    binary, entries, closing, index = read_shortcuts(original_vdf)
    data, ns, collections, version = parse_collections(cloud, namespaces)
    print(f"Steam profile: {user.name}")
    owners = [e for e in entries if owned(e)]
    own_by_rom = {get_path(e): e for e in owners}
    known_by_rom = {get_path(e): e for e in entries if get_path(e)}
    all_ids = {e["appid"] & 0xffffffff for e in entries if isinstance(e["appid"], int)}
    titles_in_use = {str(e["name"]).casefold() for e in entries}
    members = {}
    for group in CATEGORIES:
        row = collections.get(group.casefold())
        members[group] = set(row[1].get("added", [])) if row else set()
    new_entries, assignments = [], {"Switch": set(), "Switch 2": set()}
    additions = skipped = matches = 0
    artwork_apps = []
    if args.mode == "artwork":
        for entry in owners:
            if isinstance(entry["appid"], int):
                artwork_apps.append((entry["appid"] & 0xffffffff, str(entry["name"])))
        if not artwork_apps:
            print("No Lichii-managed Steam shortcuts found for artwork.")
            return
        scrape_apps(user, artwork_apps, args)
        return
    if args.mode == "clear":
        remove_ids = {e["appid"] & 0xffffffff for e in owners if isinstance(e["appid"], int)}
        if not remove_ids:
            print("No Lichii-managed Steam shortcuts to clear.")
            return
        print(f"Will remove ONLY {len(remove_ids)} Lichii-managed Steam shortcuts.")
        if not args.yes and input("Type CLEAR to confirm: ").strip() != "CLEAR":
            print("Canceled. Nothing changed.")
            return
        # Strip ONLY this tool's original entry spans, preserving other entries byte-for-byte.
        trimmed = binary
        for entry in sorted(owners, key=lambda e: e["start"], reverse=True):
            trimmed = trimmed[:entry["start"]] + trimmed[entry["stop"]:]
        binary = trimmed
        collection_changes = 0
        version += 1
        for group, (pos, doc) in list(collections.items()):
            if "filterSpec" in doc:
                continue
            ids = set(doc.get("added", [])) & remove_ids
            if ids:
                collection_changes += bool(update_collection(
                    data, collections, doc["name"], remove_ids=ids, version=version))
        print(f"Removed: {len(remove_ids)} managed shortcuts; updated {collection_changes} collections.")
    else:
        roots = scan_roots(args.rom_root)
        if not roots:
            abort("No Lichii ROM folders detected. Use --rom-root /path/to/games.")
        print("ROM folders:", *map(str, roots), sep="\n  ")
        for rom in roms_in(roots):
            reason = non_game_package_reason(rom)
            if reason:
                print(f"SKIP {reason}: {rom.name}")
                skipped += 1
                continue
            group = classify(rom, args.mode)
            if group is None:
                print(f"SKIP unclassified: {rom.name} (put in Switch or Switch 2 folder)")
                skipped += 1
                continue
            if args.mode == "switch" and group != "Switch":
                continue
            if args.mode == "switch2" and group != "Switch 2":
                continue
            name = rom.stem.replace("_", " ").strip()
            existing = own_by_rom.get(str(rom)) or known_by_rom.get(str(rom))
            if existing and isinstance(existing["appid"], int):
                appid = existing["appid"] & 0xffffffff
                matches += 1
            else:
                # If a game with this name is already in target collection, don't duplicate it.
                names = {str(e["name"]).casefold() for e in entries
                         if isinstance(e["appid"], int)
                         and (e["appid"] & 0xffffffff) in members[group]}
                if name.casefold() in names:
                    print(f"EXISTING IN {group}: {name}")
                    skipped += 1
                    continue
                # Titles need unique app IDs even for cross-generation same-name ports.
                if name.casefold() in titles_in_use:
                    name = f"{name} [{group}]"
                if name.casefold() in titles_in_use:
                    name = f"{name} [{zlib.crc32(str(rom).encode('utf-8')):08x}]"
                exe = '"' + str(SCRIPT) + '"'
                appid = (zlib.crc32((exe + name).encode("utf-8")) | 0x80000000) & 0xffffffff
                if appid in all_ids:
                    print(f"SKIP AppID collision: {name}")
                    skipped += 1
                    continue
                all_ids.add(appid)
                titles_in_use.add(name.casefold())
                new_entries.append(make_shortcut(index, appid, name, rom))
                index += 1
                additions += 1
                print(f"ADD {group}: {name} (fullscreen)")
            assignments[group].add(appid)
            artwork_apps.append((appid, str(existing["name"]) if existing else name))
        if not new_entries and not any(assignments.values()):
            print(f"No changes. Skipped/unclassified: {skipped}")
            return
        binary = binary[:closing] + b"".join(new_entries) + binary[closing:]
        version += 1
        updated = 0
        for group in CATEGORIES:
            if assignments[group]:
                updated += bool(update_collection(
                    data, collections, group, add_ids=assignments[group], version=version))
        print(f"New shortcuts: {additions}; existing ROM matches: {matches}; "
              f"skipped: {skipped}; updated collections: {updated}")
    if binary == original_vdf and (collection_changes if args.mode == "clear" else updated) == 0:
        print("Steam shortcuts and collections already synchronized.")
        if args.mode != "clear":
            scrape_apps(user, artwork_apps, args)
        return
    if args.dry_run:
        print("DRY RUN: No Steam files changed.")
        if args.mode != "clear":
            scrape_apps(user, artwork_apps, args)
        return
    # Sync the Steam cloud namespace version to the one used by the changed collections.
    for row in ns:
        if isinstance(row, list) and len(row) == 2 and str(row[0]) == "1":
            row[1] = str(version)
    output_cloud = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    output_ns = json.dumps(ns, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if binary == original_vdf and output_cloud == original_cloud and output_ns == original_ns:
        print("Already synchronized; nothing changed.")
        return
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = BACKUPS / stamp
    target.mkdir(parents=True, exist_ok=False)
    for path, blob in ((shortcuts, original_vdf), (cloud, original_cloud),
                       (namespaces, original_ns)):
        (target / path.name).write_bytes(blob)
    print(f"BACKUP: {target}")
    # Steam must remain stopped; recheck immediately before changing files.
    if steam_running():
        abort("Steam started during import. Nothing changed; close Steam and retry.")
    # Avoid overwriting edits made after we read the originals.
    for path, old in ((shortcuts, original_vdf), (cloud, original_cloud),
                      (namespaces, original_ns)):
        if (path.read_bytes() if path.exists() else b"\x00shortcuts\x00\x08\x08") != old:
            abort(f"Steam file changed while preparing: {path}")
    atomic_write(shortcuts, binary)
    atomic_write(cloud, output_cloud)
    atomic_write(namespaces, output_ns)
    print("SUCCESS: Steam shortcuts and collections updated.")
    print("Restart Steam to see the changes. If Steam cloud restores older collections, "
          "restore the backed-up files and report this to the project.")
    if args.mode != "clear":
        scrape_apps(user, artwork_apps, args)


def main():
    p = argparse.ArgumentParser(description="Lichii Steam Integration: Switch and Switch 2")
    p.add_argument("--mode", choices=["switch", "switch2", "all", "clear", "artwork"], default="all")
    p.add_argument("--rom-root", action="append", default=[],
                   help="Extra ROM folder to scan (repeatable)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true", help="Confirm clear (use with caution)")
    p.add_argument("--no-artwork", action="store_true",
                   help="Skip optional SteamGridDB artwork scraping")
    p.add_argument("--configure-artwork", action="store_true",
                   help="Store your SteamGridDB API key locally, without importing games")
    args = p.parse_args()
    try:
        if args.configure_artwork:
            get_artwork_module().configure_key()
            return
        do_import(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

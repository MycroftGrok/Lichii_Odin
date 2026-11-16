#!/usr/bin/env python3
"""Manual SteamGridDB search after Lichii's normal artwork lookup fails.

Never removes or overwrites Steam artwork. Queue and search are read-only;
preview downloads to a private cache only; install requires explicit consent
and a closed Steam client.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
LOG_FILE = Path.home() / '.local/share/lichii/logs/steam-integration-latest.log'


def sibling(filename: str, name: str):
    path = HERE / filename
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f'Missing/symlinked Lichii helper: {path}')
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load helper: {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def library(steam):
    """Only shortcuts owned by Lichii and visible in Lichii's current ROM roots."""
    user, shortcuts, _, _ = steam.discover_steam()
    _, entries, _, _ = steam.read_shortcuts(shortcuts.read_bytes())
    with contextlib.redirect_stdout(io.StringIO()):
        roots = steam.scan_roots([])
    visible = {str(path) for path in steam.roms_in(roots)
               if not steam.non_game_package_reason(path)
               and steam.classify(path, 'all') is not None}
    result = {}
    for entry in entries:
        if not steam.owned(entry) or not isinstance(entry['appid'], int):
            continue
        rom = steam.get_path(entry)
        if rom not in visible:
            continue
        appid = entry['appid'] & 0xffffffff
        if appid in result:
            raise RuntimeError(f'Colliding Lichii AppID: {appid}; refusing manual artwork')
        result[appid] = {'appid': appid, 'title': str(entry['name']),
                         'rom': rom, 'user': user}
    return result


def missing_types(art, grid: Path, appid: int):
    return [(label, endpoint, dims, suffix) for label, endpoint, dims, suffix
            in art.ARTWORK_TYPES if not art.existing_art(grid, appid, suffix)]


def scraped_titles_from_log(path: Path = LOG_FILE):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 5 * 1024 * 1024:
        return set()
    content = path.read_text(encoding='utf-8', errors='replace')
    if not re.search(r'(?m)^Result: finished\s*$', content):
        return set()
    return {m.group(1).strip() for m in re.finditer(r'(?m)^ARTWORK: (.+)$', content)}


def fallback_queue(steam, art, latest_only=False, log_file=LOG_FILE):
    scanned = scraped_titles_from_log(log_file) if latest_only else None
    rows = []
    for appid, row in library(steam).items():
        if scanned is not None and row['title'] not in scanned:
            continue
        grid = row['user'] / 'config/grid'
        missing = missing_types(art, grid, appid)
        # User requirement: pop up ONLY when every scrape method yielded no usable artwork.
        if len(missing) != len(art.ARTWORK_TYPES):
            continue
        rows.append({'appid': appid, 'title': row['title'],
                     'suggestion': art.search_title(row['title']),
                     'missing': [x[0] for x in missing]})
    return rows


def validate_query(value):
    if not isinstance(value, str) or not (2 <= len(value.strip()) <= 120):
        raise ValueError('Search must contain between 2 and 120 characters')
    if any(ord(c) < 32 for c in value):
        raise ValueError('Search text contains control characters')
    return value.strip()


def candidates(art, query, key):
    query = validate_query(query)
    rows = art.request_json('/search/autocomplete/' + quote(query, safe=''), key)
    found = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        game_id, title = row.get('id'), row.get('name')
        if type(game_id) is not int or game_id <= 0 or not isinstance(title, str):
            continue
        date = row.get('release_date')
        year = None
        if type(date) is int and 0 < date < 32503680000:
            year = datetime.datetime.fromtimestamp(date, datetime.timezone.utc).year
        found[game_id] = {'id': game_id, 'name': title, 'year': year,
                          'url': f'https://www.steamgriddb.com/game/{game_id}'}
    return list(found.values())[:40]


def confirm_candidate(art, query, game_id, key):
    if type(game_id) is not int or game_id <= 0:
        raise ValueError('Invalid SteamGridDB game ID')
    if game_id not in {entry['id'] for entry in candidates(art, query, key)}:
        raise RuntimeError('Selected SteamGridDB game is no longer in the search results')


def artwork_previews(art, game_id, key):
    cache_root = Path.home() / '.cache/lichii/manual-artwork-previews'
    if cache_root.is_symlink() or cache_root.parent.is_symlink():
        raise RuntimeError('Refusing symlinked artwork preview folder')
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_root.chmod(0o700)
    directory = Path(tempfile.mkdtemp(prefix='preview-', dir=cache_root))
    rows = []
    for number, (label, endpoint, dims, _suffix) in enumerate(art.ARTWORK_TYPES):
        route = f'/{endpoint}/game/{game_id}'
        if dims:
            route += '?dimensions=' + quote(dims, safe=',')
        try:
            items = art.request_json(route, key)
        except (RuntimeError, ValueError, OSError):
            continue
        for item in items[:15]:
            if not isinstance(item, dict) or item.get('type') == 'animated':
                continue
            url = item.get('url')
            if not isinstance(url, str):
                continue
            try:
                blob, ext = art.load_image(url, 'icon' if endpoint == 'icons' else endpoint)
                destination = directory / f'{number}{ext}'
                destination.write_bytes(blob)
                rows.append({'type': label, 'file': str(destination)})
                break
            except (OSError, ValueError, RuntimeError):
                continue
    return rows


def install_missing(art, grid, appid, game_id, key, before_write=None):
    """Use only SGDB-approved URLs; no overwrites even on competing extensions."""
    installed = 0
    failures = []
    for label, endpoint, dims, suffix in missing_types(art, grid, appid):
        route = f'/{endpoint}/game/{game_id}'
        if dims:
            route += '?dimensions=' + quote(dims, safe=',')
        try:
            items = art.request_json(route, key)
        except (RuntimeError, ValueError, OSError) as exc:
            failures.append(f'{label}: {exc}')
            continue
        for item in items[:30]:
            if not isinstance(item, dict) or item.get('type') == 'animated':
                continue
            url = item.get('url')
            if not isinstance(url, str):
                continue
            try:
                blob, ext = art.load_image(url, 'icon' if endpoint == 'icons' else endpoint)
                if art.existing_art(grid, appid, suffix):
                    break
                if grid.is_symlink():
                    raise RuntimeError('Refusing symlinked Steam artwork folder')
                if any((grid / f'{appid}{suffix}{e}').is_symlink()
                       for e in ('.png', '.jpg', '.jpeg', '.ico', '.webp')):
                    raise RuntimeError('Refusing symlinked destination artwork file')
                if before_write is not None:
                    before_write()
                art.save_art(grid, f'{appid}{suffix}{ext}', blob)
                if art.existing_art(grid, appid, suffix):
                    installed += 1
                break
            except InterruptedError:
                raise
            except (OSError, ValueError, RuntimeError) as exc:
                failures.append(f'{label}: {exc}')
        else:
            failures.append(f'{label}: no usable images')
    return installed, failures


def main(argv=None):
    parser = argparse.ArgumentParser(description='Lichii manual artwork fallback')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--queue', action='store_true', help='List games with zero artwork')
    mode.add_argument('--search', action='store_true', help='Search SGDB without exact-title restriction')
    mode.add_argument('--preview', action='store_true', help='Download candidate previews to private cache')
    mode.add_argument('--apply', action='store_true', help='Install missing art after confirmation')
    parser.add_argument('--only-latest', action='store_true', help='Queue only games attempted in latest completed scrape')
    parser.add_argument('--appid', type=int)
    parser.add_argument('--query')
    parser.add_argument('--game-id', type=int)
    parser.add_argument('--confirm', choices=['INSTALL-MISSING-ARTWORK'])
    args = parser.parse_args(argv)
    steam = sibling('steam-integration.py', 'lichii_steam_for_manual_art')
    art = sibling('steam_artwork.py', 'lichii_artwork_for_manual_art')
    if args.queue:
        print(json.dumps(fallback_queue(steam, art, args.only_latest), ensure_ascii=False))
        return
    if args.appid is None or args.appid <= 0:
        raise ValueError('Specify a valid managed Steam AppID')
    games = library(steam)
    game = games.get(args.appid)
    if game is None:
        raise RuntimeError('AppID is not a managed, visible Lichii ROM shortcut')
    if len(missing_types(art, game['user'] / 'config/grid', args.appid)) != len(art.ARTWORK_TYPES):
        raise RuntimeError('Game now has artwork; manual fallback is no longer needed')
    key = art.token()
    if not key:
        raise RuntimeError('SteamGridDB API key missing. Configure it in the Steam menu first')
    query = validate_query(args.query)
    if args.search:
        print(json.dumps(candidates(art, query, key), ensure_ascii=False))
        return
    confirm_candidate(art, query, args.game_id, key)
    if args.preview:
        print(json.dumps(artwork_previews(art, args.game_id, key), ensure_ascii=False))
        return
    if args.confirm != 'INSTALL-MISSING-ARTWORK':
        raise RuntimeError('Explicit artwork installation confirmation is required')
    if steam.steam_running():
        raise RuntimeError('Steam is still running. Close Steam completely before installing artwork')
    grid = game['user'] / 'config/grid'
    def ensure_stopped():
        if steam.steam_running():
            raise InterruptedError('Steam started while preparing artwork; operation stopped')
    got, failures = install_missing(art, grid, args.appid, args.game_id, key,
                                     before_write=ensure_stopped)
    if steam.steam_running():
        raise RuntimeError('Steam started during artwork installation. Close Steam and inspect artwork')
    if got:
        steam.set_shortcut_icons(game['user'], allowed_appids={args.appid})
    print(json.dumps({'installed': got, 'missing': len(missing_types(art, grid, args.appid)),
                      'issues': failures[:10]}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        sys.exit(1)

#!/usr/bin/env python3
"""Guarded, explicit removal of Lichii-owned duplicate Steam shortcuts.

Default is read-only. Never deletes ROMs, saves, artwork, or unrelated Steam shortcuts.
Uses a SHA-256 plan token, closed-Steam check, originals backup, and undo manifest.
"""
from __future__ import annotations
import argparse
import copy
import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import steam_duplicate_manager as duplicate

BACKUP_ROOT = Path.home() / '.local/share/lichii/steam-integration-backups'
CONFIRM = 'REMOVE-ONLY-SELECTED'


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def digest(b):
    return hashlib.sha256(b).hexdigest()


def u32(x):
    # Steam can represent a collection ID with signed or unsigned 32-bit decimal.
    if isinstance(x, bool) or not isinstance(x, (str, int)):
        raise ValueError('Non-numeric Steam collection AppID')
    try:
        n = int(x)
    except ValueError as exc:
        raise ValueError('Non-numeric Steam collection AppID') from exc
    if not (-(1 << 31) <= n < (1 << 32)):
        raise ValueError('Steam collection AppID out of supported range')
    return n & 0xffffffff


def formatted_id(appid, reference):
    n = appid if int(reference) >= 0 else (appid if appid < 2**31 else appid - 2**32)
    return str(n) if isinstance(reference, str) else n


def update_memberships(cloud_blob, ns_blob, removed_ids, keep_id):
    """Return updated collection/namespace bytes, counts; fail closed on unsupported rows."""
    data = json.loads(cloud_blob)
    ns = json.loads(ns_blob)
    require(isinstance(data, list) and isinstance(ns, list), 'Unexpected Steam collections JSON shape')
    version_rows = [row for row in ns if isinstance(row, list) and len(row) == 2 and str(row[0]) == '1'
                    and str(row[1]).isdigit()]
    require(version_rows, 'Steam namespace version 1 not found')
    version = max(int(row[1]) for row in version_rows)
    seen_names = set()
    affected = 0
    for row in data:
        require(isinstance(row, list) and len(row) == 2, 'Unexpected cloud storage row')
        key, value = row
        if not (isinstance(key, str) and key.startswith('user-collections.')):
            continue
        require(isinstance(value, dict), 'Unexpected Steam collection value')
        if value.get('is_deleted'):
            continue
        require(isinstance(value.get('value'), str), 'Missing Steam collection document')
        doc = json.loads(value['value'])
        require(isinstance(doc, dict) and isinstance(doc.get('name'), str), 'Unrecognized collection document')
        name = doc['name'].casefold()
        require(name not in seen_names, 'Duplicate Steam collection names; cannot safely update')
        seen_names.add(name)
        added, excluded = doc.get('added', []), doc.get('removed', [])
        require(isinstance(added, list) and isinstance(excluded, list), 'Unsupported collection membership')
        for x in added + excluded:
            u32(x)
        had = [x for x in added if u32(x) in removed_ids]
        rejected = [x for x in excluded if u32(x) in removed_ids]
        if not (had or rejected):
            continue
        require('filterSpec' not in doc, f'Dynamic collection {doc["name"]} references duplicate; aborting')
        require(keep_id not in {u32(x) for x in excluded},
                f'Keeper is explicitly excluded from {doc["name"]}; aborting')
        new_added = [x for x in added if u32(x) not in removed_ids]
        new_excluded = [x for x in excluded if u32(x) not in removed_ids]
        # Preserve the union of positive memberships only, not explicit exclusions.
        if had and keep_id not in {u32(x) for x in new_added}:
            new_added.append(formatted_id(keep_id, had[0]))
        doc['added'], doc['removed'] = new_added, new_excluded
        value['value'] = json.dumps(doc, ensure_ascii=False, separators=(',', ':'))
        affected += 1
    if not affected:
        return cloud_blob, ns_blob, 0
    new_version = max(version, *[int(row[1].get('version', 0)) for row in data
                                 if isinstance(row[1], dict)
                                 and str(row[1].get('version', '0')).isdigit()]) + 1
    old_data = json.loads(cloud_blob)
    for row, old in zip(data, old_data):
        if row != old:
            row[1]['version'] = str(new_version)
            row[1]['timestamp'] = int(datetime.datetime.now().timestamp())
    for row in version_rows:
        row[1] = str(new_version)
    return (json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode(),
            json.dumps(ns, ensure_ascii=False, separators=(',', ':')).encode(), affected)


def calculate(steam, blobs, keep_appid, visible=None):
    """Pure computation: untouched source blobs in, exact proposed bytes and summary out."""
    vdf, cloud, namespaces = blobs
    binary, entries, _closing, _next = steam.read_shortcuts(vdf)
    require(binary == vdf, 'Unexpected shortcuts normalization')
    ids = [e['appid'] & 0xffffffff for e in entries if isinstance(e.get('appid'), int)]
    require(len(ids) == len(set(ids)), 'Duplicate Steam AppIDs detected; cannot safely remove entries')
    groups = duplicate.duplicate_groups(entries, steam)
    matching = [(path, group) for path, group in groups.items()
                if any((e['appid'] & 0xffffffff) == keep_appid for e in group)]
    require(len(matching) == 1, 'Keeper AppID must belong to exactly one duplicate ROM group')
    rom, group = matching[0]
    require(visible is None or rom in visible,
            'Duplicate ROM is not currently visible in the configured Lichii game library')
    keep = [e for e in group if (e['appid'] & 0xffffffff) == keep_appid]
    require(len(keep) == 1 and steam.owned(keep[0]), 'Keeper is not a unique Lichii-owned shortcut')
    removing = [e for e in group if (e['appid'] & 0xffffffff) != keep_appid]
    require(removing, 'No additional Lichii-owned shortcuts to remove')
    remove_ids = {e['appid'] & 0xffffffff for e in removing}
    output = binary
    for e in sorted(removing, key=lambda e: e['start'], reverse=True):
        require(0 <= e['start'] < e['stop'] <= len(output), 'Invalid Steam shortcut byte span')
        require(output[e['start']] == 0, 'Steam shortcut object span has changed')
        output = output[:e['start']] + output[e['stop']:]
    _, check_entries, _, _ = steam.read_shortcuts(output)
    require(len(check_entries) == len(entries) - len(removing), 'Post-removal shortcut count mismatch')
    require(any((x.get('appid') & 0xffffffff) == keep_appid for x in check_entries
                if isinstance(x.get('appid'), int)), 'Keeper vanished from modified Steam shortcuts')
    require(not any((x.get('appid') & 0xffffffff) in remove_ids for x in check_entries
                    if isinstance(x.get('appid'), int)), 'Duplicate remained after modification')
    new_cloud, new_ns, changed = update_memberships(cloud, namespaces, remove_ids, keep_appid)
    fingerprint = hashlib.sha256()
    for b in blobs:
        fingerprint.update(len(b).to_bytes(8, 'big'))
        fingerprint.update(b)
    fingerprint.update(str(keep_appid).encode('ascii'))
    token = fingerprint.hexdigest()
    return {
        'keeper_appid': keep_appid,
        'keeper_name': str(keep[0]['name']),
        'rom_path': rom,
        'removed_appids': sorted(remove_ids),
        'removed_names': [str(e['name']) for e in removing],
        'removed_shortcuts': len(removing),
        'collections_changed': changed,
        'plan_token': token,
    }, (output, new_cloud, new_ns)


def read_live(steam):
    user, shortcuts, cloud, namespaces = steam.discover_steam()
    for p in (shortcuts, cloud, namespaces):
        require(p.is_file() and not p.is_symlink(), f'Steam file missing or symlinked: {p}')
    return user, (shortcuts, cloud, namespaces), tuple(p.read_bytes() for p in (shortcuts, cloud, namespaces))


def prepare_live(steam, keep_appid):
    user, paths, blobs = read_live(steam)
    roots = steam.scan_roots([])
    visible = {str(path) for path in steam.roms_in(roots)
               if not steam.non_game_package_reason(path) and steam.classify(path, 'all') is not None}
    summary, output = calculate(steam, blobs, keep_appid, visible)
    grid = user / 'config/grid'
    keeper_art = duplicate.artworks(grid, keep_appid)
    for removed in summary['removed_appids']:
        removal_art = duplicate.artworks(grid, removed)
        lost_types = [kind for kind, files in removal_art.items()
                      if files and not keeper_art.get(kind)]
        require(not lost_types,
                f'Keeper lacks {", ".join(lost_types)} artwork present on duplicate AppID {removed}; '
                'choose a keeper with that artwork or copy images before removal')
    summary['steam_profile'] = user.name
    summary['mode'] = 'PREVIEW ONLY — NO STEAM FILES MODIFIED'
    summary['artwork_policy'] = 'Keep all existing artwork files, including duplicate AppID art; no image files modified.'
    return paths, blobs, summary, output


def apply_live(steam, keep_appid, expected_token, confirm):
    require(confirm == CONFIRM, 'Explicit removal confirmation phrase missing')
    require(not steam.steam_running(), 'Steam must be closed; no shutdown requested or attempted')
    paths, before, summary, after = prepare_live(steam, keep_appid)
    require(hmac.compare_digest(summary['plan_token'], expected_token),
            'Preview is stale or source data changed; reopen Duplicate Manager')
    root = BACKUP_ROOT
    require(not root.is_symlink(), 'Steam backup root is a symlink')
    root.mkdir(parents=True, exist_ok=True)
    target = root / (datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-duplicate-remove')
    target.mkdir(mode=0o700)
    try:
        for p, b in zip(paths, before):
            dest = target / p.name
            with dest.open('xb') as file:
                file.write(b)
            dest.chmod(0o600)
            require(dest.read_bytes() == b, 'Backup verification failed')
        manifest = {'version': 1, 'kind': 'lichii-duplicate-removal',
                    'keeper_appid': keep_appid,
                    'removed_appids': summary['removed_appids'],
                    'files': [{'name': p.name, 'path': str(p), 'before_sha256': digest(old),
                               'after_sha256': digest(new)}
                              for p, old, new in zip(paths, before, after)]}
        mfile = target / 'undo-manifest.json'
        mfile.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        mfile.chmod(0o600)
        require(json.loads(mfile.read_text()) == manifest, 'Undo manifest verification failed')
        require(not steam.steam_running(), 'Steam restarted before metadata modification')
        for p, old in zip(paths, before):
            require(not p.is_symlink() and p.read_bytes() == old,
                    f'Steam file changed while preparing: {p}')
        written = []
        try:
            for p, old, new in zip(paths, before, after):
                if old != new:
                    require(not steam.steam_running(), 'Steam restarted during metadata write')
                    steam.atomic_write(p, new)
                    written.append((p, old, new))
            for p, new in zip(paths, after):
                require(p.read_bytes() == new, f'Post-write Steam metadata mismatch: {p}')
        except Exception:
            # Only revert our own byte-exact writes if there have been no further changes.
            if not steam.steam_running():
                for p, old, new in reversed(list(zip(paths, before, after))):
                    if old != new and p.is_file() and not p.is_symlink() and p.read_bytes() == new:
                        steam.atomic_write(p, old)
            raise
        summary['mode'] = 'APPLIED — restart Steam to refresh the library'
        summary['backup'] = str(target)
        return summary
    except Exception:
        print('RECOVERY BACKUP:', target, file=sys.stderr)
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--keep-appid', type=int, required=True)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--confirm-token', default='')
    p.add_argument('--confirm', default='')
    p.add_argument('--json', action='store_true')
    args = p.parse_args(argv)
    require(0 < args.keep_appid <= 0xffffffff, 'Keeper AppID out of range')
    steam = duplicate.load_steam(HERE / 'steam-integration.py')
    if args.apply:
        result = apply_live(steam, args.keep_appid, args.confirm_token, args.confirm)
    else:
        _paths, _blobs, result, _after = prepare_live(steam, args.keep_appid)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        sys.exit(1)

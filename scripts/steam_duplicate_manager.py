#!/usr/bin/env python3
"""Read-only Steam duplicate shortcut inspector for Lichii on ArmadaOS.

No Steam writes, process termination, or cache changes. Designed to be extended
with guarded apply after preview logic is tested against real data.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
SUFFIXES = ('p', '', '_hero', '_logo', '_icon')
EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.ico')


def load_steam(script: Path):
    spec = importlib.util.spec_from_file_location('lichii_steam_duplicates_dependency', script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load {script}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def duplicate_groups(entries, steam):
    paths = defaultdict(list)
    for e in entries:
        if not steam.owned(e) or not isinstance(e.get('appid'), int):
            continue
        path = steam.get_path(e)
        if path:
            paths[path].append(e)
    return {k: v for k, v in paths.items() if len(v) > 1}


def artworks(grid: Path, appid: int):
    found = {}
    for suffix in SUFFIXES:
        found[suffix or 'landscape'] = [str(grid / f'{appid}{suffix}{ext}')
                                         for ext in EXTENSIONS
                                         if (grid / f'{appid}{suffix}{ext}').is_file()]
    return found


def collection_memberships(cloud_path: Path, appids: set[int]):
    """Report collection memberships only; never mutate collections."""
    raw = json.loads(cloud_path.read_text(encoding='utf-8'))
    result = {str(i): [] for i in appids}
    for row in raw:
        if not isinstance(row, list) or len(row) != 2 or not isinstance(row[1], dict):
            continue
        try:
            doc = json.loads(row[1]['value'])
        except (KeyError, TypeError, ValueError):
            continue
        if not isinstance(doc, dict):
            continue
        added = doc.get('added', [])
        for appid in appids:
            # Steam collections may serialize IDs as signed or unsigned strings.
            signed = appid if appid < 2**31 else appid - 2**32
            if str(appid) in map(str, added) or str(signed) in map(str, added):
                result[str(appid)].append(str(doc.get('name', '<unnamed>')))
    return result


def build_report(entries, steam, grid: Path, memberships=None):
    groups = duplicate_groups(entries, steam)
    report = []
    for path, copies in sorted(groups.items()):
        listings = []
        for e in copies:
            appid = e['appid'] & 0xffffffff
            a = artworks(grid, appid)
            listings.append({
                'appid': appid, 'name': str(e['name']), 'rom_path': path,
                'artwork_types_present': sum(bool(files) for files in a.values()),
                'artwork': a, 'collections': (memberships or {}).get(str(appid), []),
            })
        report.append({'rom_path': path, 'shortcuts': listings})
    return report


def preview(report, keep_appid):
    selected = [g for g in report if any(x['appid'] == keep_appid for x in g['shortcuts'])]
    if len(selected) != 1:
        raise ValueError('Keep AppID must identify exactly one shortcut in a duplicate group')
    group = selected[0]
    keep = next(x for x in group['shortcuts'] if x['appid'] == keep_appid)
    remove = [x for x in group['shortcuts'] if x['appid'] != keep_appid]
    return {
        'mode': 'PREVIEW ONLY — NO FILES WILL BE CHANGED',
        'rom_path': group['rom_path'], 'keep': keep,
        'would_remove': remove,
        'collection_names_to_review': sorted(set(n for x in remove for n in x['collections'])),
        'missing_artwork_on_keeper': [kind for kind, files in keep['artwork'].items() if not files],
        'warning': 'No operation is applied. Transfers must not overwrite existing custom art.',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview-keep-appid', type=int, default=None)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    script = Path(__file__).with_name('steam-integration.py')
    if not script.is_file():
        parser.error(f'Missing sibling {script.name}: install in Lichii source/scripts')
    steam = load_steam(script)
    user, shortcuts, cloud, _namespaces = steam.discover_steam()
    _, entries, _, _ = steam.read_shortcuts(shortcuts.read_bytes())
    groups = duplicate_groups(entries, steam)
    ids = {e['appid'] & 0xffffffff for copies in groups.values() for e in copies}
    memberships = collection_memberships(cloud, ids)
    report = build_report(entries, steam, user / 'config/grid', memberships)
    if args.preview_keep_appid is not None:
        output = preview(report, args.preview_keep_appid)
    else:
        output = {'mode': 'READ ONLY', 'total_steam_shortcuts': len(entries),
                  'lichii_managed_shortcuts': sum(steam.owned(e) for e in entries),
                  'duplicate_groups': len(report), 'groups': report}
    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    elif args.preview_keep_appid is not None:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print('Total Steam shortcuts:', output['total_steam_shortcuts'])
        print('Lichii-managed shortcuts:', output['lichii_managed_shortcuts'])
        print('Duplicate ROM groups:', output['duplicate_groups'])
        for group in report:
            print('\nROM:', group['rom_path'])
            for item in group['shortcuts']:
                print('  AppID:', item['appid'], '|', item['name'],
                      '| artwork:', f"{item['artwork_types_present']}/5",
                      '| collections:', ', '.join(item['collections']) or '(none)')
        print('\nNo changes made to Steam.')


if __name__ == '__main__':
    main()

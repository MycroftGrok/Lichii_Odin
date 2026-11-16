#!/usr/bin/env python3
"""Read-only statistics, diagnostics, and exports for Lichii Steam Integration.
No Steam metadata writes. Sensitive API credentials are never read.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

LOG = Path.home() / '.local/share/lichii/logs/steam-integration-latest.log'


def parse(text):
    lines = text.splitlines()
    def first(prefix, fallback=''):
        return next((s[len(prefix):].strip() for s in lines if s.startswith(prefix)), fallback)
    mode = first('Action:', 'unknown')
    result = first('Result:', 'unknown')
    stats = {
        'action': mode, 'started': first('Started:'), 'finished': first('Finished:'),
        'result': result, 'errors': sum(bool(re.search(r'\b(?:ERROR|Traceback|failed:)', line, re.I)) for line in lines),
        'items': [],
    }
    if result != 'finished' and stats['errors'] == 0:
        stats['errors'] = 1
    if mode == 'artwork':
        seen = []
        by_game = {}
        current = None
        files = 0
        for line in lines:
            if line.startswith('ARTWORK: '):
                current = line[9:].strip()
                seen.append(current)
                by_game.setdefault(current, {'installed': 0, 'missing_reason': ''})
            elif current and re.search(r'^  (?:portrait cover|landscape cover|hero background|transparent logo|icon): installed$', line):
                by_game[current]['installed'] += 1
                files += 1
            elif current and ('No exact SteamGridDB match:' in line or 'Ambiguous SteamGridDB matches' in line):
                by_game[current]['missing_reason'] = line.strip()
        stats.update({'games_detected': len(seen),
                      'games_updated': sum(v['installed'] > 0 for v in by_game.values()),
                      'games_missing_artwork': sum(bool(v['missing_reason']) for v in by_game.values()),
                      'artwork_files_installed': files,
                      'missing_artwork_files': int((re.search(r'Artwork summary: \d+ installed; (\d+) missing/unmatched assets', text) or [None, 0])[1]),
                      'shortcut_icons_updated': int((re.search(r'Updated (\d+) Steam shortcut icon paths', text) or [None, 0])[1]),
                      'items': [{'name': name, **data} for name, data in by_game.items()]})
    elif mode in ('switch','switch2','all'):
        added = [line[4:].strip() for line in lines if line.startswith('ADD ')]
        skipped = [line for line in lines if line.startswith(('SKIP ', 'EXISTING IN '))]
        summary = re.search(r'New shortcuts: (\d+); existing ROM matches: (\d+); skipped: (\d+); updated collections: (\d+)', text)
        stats.update({'new_games_discovered': int(summary[1]) if summary else len(added),
                      'games_imported_to_steam': int(summary[1]) if summary and result == 'finished' else 0,
                      'games_not_imported': int(summary[3]) if summary else len(skipped),
                      'existing_rom_matches': int(summary[2]) if summary else 0,
                      'collections_updated': int(summary[4]) if summary else 0,
                      'items': [{'status':'skipped','detail':s} for s in skipped]})
        # New games discovered here means new shortcuts *proposed* by this operation,
        # not all scanned ROMs; existing game matches are counted separately.
    elif mode == 'clear':
        match = re.search(r'Removed: (\d+) managed shortcuts; updated (\d+) collections', text)
        found = re.search(r'Will remove ONLY (\d+) Lichii-managed Steam shortcuts', text)
        stats.update({'managed_shortcuts_found': int(found[1]) if found else 0,
                      'shortcuts_removed': int(match[1]) if match and result == 'finished' else 0,
                      'collections_updated': int(match[2]) if match else 0})
        stats['shortcuts_retained'] = max(0, stats['managed_shortcuts_found'] - stats['shortcuts_removed'])
    return stats


def format_summary(d):
    labels = {'new_games_discovered':'New games discovered',
              'games_imported_to_steam':'Games imported to Steam',
              'games_not_imported':'Games not imported',
              'existing_rom_matches':'Existing ROM matches',
              'games_detected':'Games detected', 'games_updated':'Games updated',
              'games_missing_artwork':'Games missing artwork',
              'artwork_files_installed':'Artwork files installed',
              'missing_artwork_files':'Missing artwork files',
              'shortcut_icons_updated':'Shortcut icons updated',
              'managed_shortcuts_found':'Managed shortcuts found',
              'shortcuts_removed':'Shortcuts removed',
              'shortcuts_retained':'Shortcuts retained',
              'collections_updated':'Collections updated', 'errors':'Errors'}
    out = [f"Lichii Steam Integration — {d['action']}",
           f"Result: {d['result']}", f"Started: {d['started']}", f"Finished: {d['finished']}", '']
    out.extend(f'{label}: {d[key]}' for key,label in labels.items() if key in d)
    return '\n'.join(out) + '\n'


def export_report(data, target):
    path = Path(target).expanduser()
    if path.exists():
        raise ValueError('Refusing to overwrite an existing report')
    if path.suffix.lower() == '.json':
        payload = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    elif path.suffix.lower() == '.csv':
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(['metric','value'])
        for key,value in data.items():
            if key != 'items': writer.writerow([key,value])
        writer.writerow([])
        writer.writerow(['item','status_or_missing_reason','artwork_installed'])
        for item in data.get('items', []):
            writer.writerow([item.get('name',item.get('detail','')),item.get('missing_reason',item.get('status','')),item.get('installed', '')])
        payload = stream.getvalue()
    elif path.suffix.lower() == '.txt':
        payload = format_summary(data) + '\n' + '\n'.join(str(row) for row in data.get('items',[])) + '\n'
    else:
        raise ValueError('Report extension must be .txt, .json or .csv')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as out:
        out.write(payload)
    return path


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--json',action='store_true')
    group.add_argument('--summary',action='store_true')
    group.add_argument('--missing',action='store_true')
    group.add_argument('--export',metavar='PATH')
    parser.add_argument('--log',type=Path,default=LOG)
    args = parser.parse_args()
    if not args.log.is_file() or args.log.is_symlink():
        parser.error('Latest integration log not found or is a symlink')
    if args.log.stat().st_size > 8 * 1024 * 1024:
        parser.error('Log too large')
    data = parse(args.log.read_text(encoding='utf-8',errors='replace'))
    if args.json: print(json.dumps(data,ensure_ascii=False))
    elif args.missing:
        for item in data.get('items',[]):
            if item.get('missing_reason') or item.get('status') == 'skipped':
                print(item.get('name',item.get('detail')), ':',item.get('missing_reason',item.get('status')))
    elif args.export: print('Saved report:',export_report(data,args.export))
    else: print(format_summary(data),end='')

if __name__ == '__main__':
    main()

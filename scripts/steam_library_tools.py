#!/usr/bin/env python3
"""Safe Steam library diagnostics for Lichii.
All commands are read-only. No deletion or overwriting of Steam data.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'steam-integration.py'


def integration():
    if not SOURCE.is_file():
        raise RuntimeError(f'Missing integration script: {SOURCE}')
    spec=importlib.util.spec_from_file_location('lichii_integration_diagnostic',SOURCE)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect():
    m=integration()
    user,shortcuts,cloud,namespaces=m.discover_steam()
    _,entries,_,_=m.read_shortcuts(shortcuts.read_bytes())
    roots=m.scan_roots([])
    roms=[p for p in m.roms_in(roots) if not m.non_game_package_reason(p) and m.classify(p,'all')]
    byrom=defaultdict(list)
    for e in entries:
        path=m.get_path(e)
        if path and m.owned(e):
            byrom[path].append({'name':str(e['name']),'appid': e['appid'] & 0xffffffff})
    dups=[{'rom':path,'shortcuts':shortcuts} for path,shortcuts in byrom.items() if len(shortcuts)>1]
    coverage={key:0 for key in ('portrait','landscape','hero','logo','icon')}
    suffixes={'portrait':'p','landscape':'','hero':'_hero','logo':'_logo','icon':'_icon'}
    grid=user/'config/grid'
    for entries_for_rom in byrom.values():
        for entry in entries_for_rom:
            appid=entry['appid']
            for kind,suffix in suffixes.items():
                if any((grid/f'{appid}{suffix}{ext}').is_file() for ext in ('.png','.jpg','.jpeg','.ico','.webp')):
                    coverage[kind]+=1
    imported=set(byrom)
    visible={str(p) for p in roms}
    return {'steam_profile':user.name,'total_shortcuts':len(entries),'managed_shortcuts':sum(map(len,byrom.values())),
            'visible_roms':len(roms),'duplicate_groups':dups,'artwork_coverage':coverage,
            'roms_not_imported':[str(p) for p in roms if str(p) not in imported],
            'managed_roms_missing_from_library':[p for p in byrom if p not in visible],
            'note':'Read-only preview. Missing ROMs may be on disconnected storage. Never auto-delete.'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--duplicates',action='store_true')
    parser.add_argument('--sync-preview',action='store_true')
    args=parser.parse_args()
    data=inspect()
    if args.json:
        print(json.dumps(data,indent=2,ensure_ascii=False));return
    print('Steam profile:',data['steam_profile'])
    print('Total shortcuts:',data['total_shortcuts'])
    print('Lichii managed:',data['managed_shortcuts'])
    print('Visible ROMs:',data['visible_roms'])
    if not args.sync_preview:
        print('Duplicate groups:',len(data['duplicate_groups']))
        for group in data['duplicate_groups']:
            print('ROM:',group['rom'])
            for entry in group['shortcuts']:
                print('  Steam ID:',entry['appid'],'NAME:',entry['name'])
    print('Artwork coverage (files per managed shortcut):')
    for kind,count in data['artwork_coverage'].items():
        print(f'  {kind}: {count}/{data["managed_shortcuts"]}')
    if not args.duplicates:
        print('Visible ROMs without managed shortcuts:',len(data['roms_not_imported']))
        for path in data['roms_not_imported']:print('  NEW:',path)
        print('Managed ROMs not currently visible:',len(data['managed_roms_missing_from_library']))
        for path in data['managed_roms_missing_from_library']:print('  UNAVAILABLE:',path)
    print('Preview only. No Steam files, artwork, or ROMs changed.')

if __name__=='__main__':
    main()

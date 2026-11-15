#!/usr/bin/env python3
"""Guarded undo for future Lichii Steam Integration operations.
Never overwrites Steam changes made after the backed-up operation.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
BACKUPS=Path.home()/'.local/share/lichii/steam-integration-backups'
SRC=HERE/'steam-integration.py'

def digest(blob): return hashlib.sha256(blob).hexdigest()

def integration():
    spec=importlib.util.spec_from_file_location('lichii_undo_integration',SRC)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def latest():
    found=sorted(BACKUPS.glob('*/undo-manifest.json'),reverse=True)
    if not found: raise RuntimeError('No rollback-safe backup manifest. Only future patched operations are eligible.')
    return found[0]

def prepare(manifest_path):
    if manifest_path.is_symlink():raise RuntimeError('Refusing symlink manifest')
    folder=manifest_path.parent
    if folder.parent.resolve()!=BACKUPS.resolve():raise RuntimeError('Backup folder outside Lichii backup root')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('version')!=1 or not isinstance(manifest.get('files'),list):raise RuntimeError('Unsupported manifest')
    m=integration()
    user,shortcuts,cloud,namespaces=m.discover_steam()
    allowed={str(x.resolve()) for x in (shortcuts,cloud,namespaces)}
    rows=[]
    for row in manifest['files']:
        path=Path(row['path']);backup=folder/row['name']
        if str(path.resolve()) not in allowed or row['name'] != path.name:
            raise RuntimeError('Manifest contains a path outside the selected Steam profile')
        if backup.is_symlink() or path.is_symlink() or not backup.is_file() or not path.is_file():
            raise RuntimeError('Backup/current file unavailable or symbolic link')
        old=backup.read_bytes();now=path.read_bytes()
        if digest(old)!=row['before_sha256']:raise RuntimeError('Backup contents have changed')
        if digest(now)!=row['after_sha256']:
            raise RuntimeError('Steam metadata has changed since this backup. Undo refused to protect newer edits.')
        rows.append((path,old,now))
    if not rows:raise RuntimeError('Empty manifest')
    return rows

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true',help='Actually restore backup files')
    parser.add_argument('--confirm',default='',help='Must be exactly RESTORE-STEAM-BACKUP')
    args=parser.parse_args()
    manifest=latest()
    print('Most recent eligible backup:',manifest.parent)
    rows=prepare(manifest)
    for path,_,_ in rows:print('  VERIFIED:',path)
    print('CAUTION: Artwork images downloaded after the backup are not removed.')
    if not args.apply:
        print('PREVIEW ONLY: No changes made. To restore, close Steam and use --apply --confirm RESTORE-STEAM-BACKUP')
        return
    if args.confirm!='RESTORE-STEAM-BACKUP':raise RuntimeError('Confirmation phrase required')
    m=integration()
    if m.steam_running():raise RuntimeError('Steam is running. Undo refused.')
    # A second check prevents overwriting a Steam update between preview and apply.
    for path,old,now in rows:
        if path.read_bytes()!=now:raise RuntimeError('Files changed while preparing undo')
    import datetime
    rescue=BACKUPS/('pre-undo-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    rescue.mkdir(parents=True,exist_ok=False)
    for path,old,now in rows:
        (rescue/path.name).write_bytes(now)
    if m.steam_running():raise RuntimeError('Steam started during undo; no files changed')
    for path,old,now in rows:
        if path.read_bytes()!=now:raise RuntimeError('Steam files changed; undo refused')
    for path,old,now in rows:
        m.atomic_write(path,old)
    print('RESTORED:',len(rows),'Steam files. Pre-undo copy:',rescue)

if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError,ValueError,KeyError,TypeError,json.JSONDecodeError) as ex:
        print('ERROR:',ex,file=sys.stderr);sys.exit(1)

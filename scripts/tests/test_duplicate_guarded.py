#!/usr/bin/env python3
"""Simulated Steam files only. No access to real Steam userdata or ROMs."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import steam_duplicate_apply as target


def shortcut(appid, name, rom, ours=True):
    return {'appid': appid, 'name': name, 'rom': rom, 'ours': ours}


class FakeSteam:
    def __init__(self, base, names=None):
        self.base = Path(base)
        self.user = self.base / 'userdata/131892822'
        self.folder = self.user / 'config'
        self.folder.mkdir(parents=True)
        self.grid = self.folder / 'grid'
        self.grid.mkdir()
        self.paths = (self.folder / 'shortcuts.vdf',
                      self.folder / 'cloud-storage-namespace-1.json',
                      self.folder / 'cloud-storage-namespaces.json')
        self.visible = Path('/games/dragon-quest.nsp')
        self.running = False
        self.writes = []

    @staticmethod
    def encode(entries):
        return b'HEADER' + b''.join(b'\x00' + json.dumps(e).encode() + b'\x08' for e in entries) + b'FOOTER'

    @staticmethod
    def read_shortcuts(blob):
        assert blob.startswith(b'HEADER') and blob.endswith(b'FOOTER')
        entries = []
        pos = len(b'HEADER')
        last = len(blob) - len(b'FOOTER')
        while pos < last:
            assert blob[pos] == 0
            stop = blob.index(b'\x08', pos) + 1
            e = json.loads(blob[pos + 1:stop - 1])
            e.update({'start': pos, 'stop': stop})
            entries.append(e)
            pos = stop
        return blob, entries, pos, len(entries)

    @staticmethod
    def owned(e):
        return e['ours']

    @staticmethod
    def get_path(e):
        return e['rom']

    def create(self, entries, docs=None):
        self.paths[0].write_bytes(self.encode(entries))
        rows = [['user-collections.' + d['name'].lower(), {
            'key': 'user-collections.' + d['name'].lower(),
            'value': json.dumps(d), 'version': '4', 'timestamp': 0
        }] for d in (docs or [])]
        self.paths[1].write_text(json.dumps(rows))
        self.paths[2].write_text(json.dumps([['1', '4']]))

    def discover_steam(self):
        return (self.user, *self.paths)

    def steam_running(self):
        return self.running

    def scan_roots(self, extra):
        assert extra == []
        return [(self.visible.parent, False)]

    def roms_in(self, roots):
        return [self.visible]

    @staticmethod
    def non_game_package_reason(rom):
        return None

    @staticmethod
    def classify(rom, mode):
        return 'Switch'

    def atomic_write(self, path, new):
        self.writes.append(str(path))
        path.write_bytes(new)


class GuardedDuplicateTests(unittest.TestCase):
    def setUp(self):
        self.ctx = tempfile.TemporaryDirectory()
        self.addCleanup(self.ctx.cleanup)
        self.steam = FakeSteam(self.ctx.name)
        self.entries = [shortcut(111, 'Keep', '/games/dragon-quest.nsp'),
                        shortcut(222, 'Remove', '/games/dragon-quest.nsp'),
                        shortcut(333, 'Other Lichii Game', '/games/other.nsp'),
                        shortcut(444, 'Unrelated Steam Game', '/games/dragon-quest.nsp', False)]
        self.docs = [{'name': 'Switch', 'added': [222, 333], 'removed': []},
                     {'name': 'Favorites', 'added': ['222'], 'removed': []},
                     {'name': 'Unrelated', 'added': [444], 'removed': []}]
        self.steam.create(self.entries, self.docs)

    def test_plan_preserves_keeper_unrelated_and_collection_union(self):
        before = tuple(p.read_bytes() for p in self.steam.paths)
        s, after = target.calculate(self.steam, before, 111, {'/games/dragon-quest.nsp'})
        self.assertEqual(s['removed_appids'], [222])
        self.assertEqual(s['collections_changed'], 2)
        _blob, entries, _, _ = self.steam.read_shortcuts(after[0])
        self.assertEqual([e['appid'] for e in entries], [111, 333, 444])
        rows = json.loads(after[1]); m = {json.loads(r[1]['value'])['name']: json.loads(r[1]['value']) for r in rows}
        self.assertEqual(m['Switch']['added'], [333, 111])
        self.assertEqual(m['Favorites']['added'], ['111'])
        self.assertEqual(m['Unrelated']['added'], [444])
        self.assertEqual(tuple(p.read_bytes() for p in self.steam.paths), before)

    def test_unsigned_signed_and_exclusions(self):
        big = 0xF0000001
        cloud = json.dumps([['user-collections.switch', {'value': json.dumps({
            'name': 'Switch', 'added': [-268435454, 22], 'removed': ['-268435454']
        }), 'version': '4'}]]).encode()
        ns = b'[["1","4"]]'
        # duplicate removed ID represented signed in a collection
        after, _, n = target.update_memberships(cloud, ns, {big + 1}, 0xF0000005)
        self.assertEqual(n, 1)
        doc = json.loads(json.loads(after)[0][1]['value'])
        self.assertEqual(doc['added'], [22, -(1 << 32) + 0xF0000005])
        self.assertEqual(doc['removed'], [])

    def test_dynamic_collection_blocks_cleanup(self):
        docs = [{'name': 'Smart', 'filterSpec': {}, 'added': [222], 'removed': []}]
        self.steam.create(self.entries, docs)
        before = tuple(p.read_bytes() for p in self.steam.paths)
        with self.assertRaisesRegex(RuntimeError, 'Dynamic collection'):
            target.calculate(self.steam, before, 111)
        self.assertEqual(tuple(p.read_bytes() for p in self.steam.paths), before)

    def test_keeper_explicitly_excluded_blocks_cleanup(self):
        self.steam.create(self.entries, [{'name': 'Switch', 'added': [222], 'removed': [111]}])
        with self.assertRaisesRegex(RuntimeError, 'explicitly excluded'):
            target.calculate(self.steam, tuple(p.read_bytes() for p in self.steam.paths), 111)

    def test_reject_unrelated_or_unknown_appid(self):
        for appid in (333, 444, 0):
            with self.assertRaises(RuntimeError):
                target.calculate(self.steam, tuple(p.read_bytes() for p in self.steam.paths), appid)

    def test_reject_duplicate_appids_even_outside_selected_group(self):
        self.entries.append(shortcut(333, 'Collision', '/games/x.nsp', False))
        self.steam.create(self.entries, self.docs)
        with self.assertRaisesRegex(RuntimeError, 'Duplicate Steam AppIDs'):
            target.calculate(self.steam, tuple(p.read_bytes() for p in self.steam.paths), 111)

    def test_stale_token_and_running_steam_cannot_write(self):
        old = tuple(p.read_bytes() for p in self.steam.paths)
        with patch.object(target, 'BACKUP_ROOT', Path(self.ctx.name) / 'backups'):
            with self.assertRaisesRegex(RuntimeError, 'stale'):
                target.apply_live(self.steam, 111, 'bad-token', target.CONFIRM)
            self.steam.running = True
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                target.apply_live(self.steam, 111, 'bad-token', target.CONFIRM)
        self.assertFalse(self.steam.writes)
        self.assertEqual(tuple(p.read_bytes() for p in self.steam.paths), old)

    def test_refuses_to_lose_keeper_artwork_coverage(self):
        (self.steam.grid / '222p.png').write_bytes(b'ORIGINAL CUSTOM PORTRAIT')
        with self.assertRaisesRegex(RuntimeError, 'Keeper lacks'):
            target.prepare_live(self.steam, 111)
        self.assertFalse(self.steam.writes)

    def test_backup_and_guarded_undo_manifest_after_apply(self):
        old = tuple(p.read_bytes() for p in self.steam.paths)
        _paths, _before, preview, _new = target.prepare_live(self.steam, 111)
        backup_root = Path(self.ctx.name) / 'backups'
        (self.steam.grid / '222p.png').write_bytes(b'CUSTOM ART')
        (self.steam.grid / '111p.png').write_bytes(b'KEEPER ART')
        with patch.object(target, 'BACKUP_ROOT', backup_root):
            result = target.apply_live(self.steam, 111, preview['plan_token'], target.CONFIRM)
        self.assertEqual(result['removed_shortcuts'], 1)
        folder = Path(result['backup'])
        manifest = json.loads((folder / 'undo-manifest.json').read_text())
        self.assertEqual(manifest['version'], 1)
        for path, original, row in zip(self.steam.paths, old, manifest['files']):
            self.assertEqual((folder / path.name).read_bytes(), original)
            self.assertEqual(row['before_sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(row['after_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual((self.steam.grid / '222p.png').read_bytes(), b'CUSTOM ART')
        with patch.object(target, 'BACKUP_ROOT', backup_root):
            with self.assertRaisesRegex(RuntimeError, 'Keeper AppID'):
                target.prepare_live(self.steam, 111)
        self.assertTrue(self.steam.writes)

    def test_real_vdf_byte_spans_when_integration_module_is_available(self):
        source = Path(__file__).resolve().parents[1] / 'steam-integration.py'
        if not source.is_file():
            self.skipTest('Real Steam integration parser is installed on Odin, not in package fixture')
        steam = target.duplicate.load_steam(source)
        rom = Path('/games/dragon-quest.nsp')
        other = Path('/games/other.nsp')
        binary = (b'\x00shortcuts\x00' +
                  steam.make_shortcut(0, 1001, 'Keep', rom) +
                  steam.make_shortcut(1, 1002, 'Remove', rom) +
                  steam.make_shortcut(2, 1003, 'Unrelated Lichii', other) +
                  b'\x08\x08')
        cloud, ns = (self.steam.paths[1].read_bytes(), self.steam.paths[2].read_bytes())
        summary, after = target.calculate(steam, (binary, cloud, ns), 1001, {str(rom)})
        _blob, entries, _closing, _n = steam.read_shortcuts(after[0])
        self.assertEqual([x['appid'] & 0xffffffff for x in entries], [1001, 1003])
        self.assertEqual(summary['removed_appids'], [1002])

    def test_existing_undo_tool_accepts_manifest_and_detects_newer_edits(self):
        undo_script = Path(__file__).resolve().parents[1] / 'steam_undo.py'
        if not undo_script.is_file():
            self.skipTest('Existing guarded undo helper is installed on Odin')
        import importlib.util
        spec = importlib.util.spec_from_file_location('lichii_test_undo', undo_script)
        undo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(undo)
        _paths, _before, preview, _new = target.prepare_live(self.steam, 111)
        root = Path(self.ctx.name) / 'backups'
        with patch.object(target, 'BACKUP_ROOT', root):
            completed = target.apply_live(self.steam, 111, preview['plan_token'], target.CONFIRM)
        manifest = Path(completed['backup']) / 'undo-manifest.json'
        with patch.object(undo, 'BACKUPS', root), patch.object(undo, 'integration', lambda: self.steam):
            rows = undo.prepare(manifest)
            self.assertEqual(len(rows), 3)
            self.steam.paths[0].write_bytes(b'USER CHANGED STEAM METADATA')
            with self.assertRaisesRegex(RuntimeError, 'changed since this backup'):
                undo.prepare(manifest)

    def test_failure_during_write_restores_our_exact_bytes(self):
        before = tuple(p.read_bytes() for p in self.steam.paths)
        _paths, _old, preview, _new = target.prepare_live(self.steam, 111)
        original_write = self.steam.atomic_write
        count = [0]
        def failing_write(path, content):
            count[0] += 1
            if count[0] == 2:
                raise OSError('simulated disk write error')
            original_write(path, content)
        self.steam.atomic_write = failing_write
        with patch.object(target, 'BACKUP_ROOT', Path(self.ctx.name) / 'backups'):
            with self.assertRaisesRegex(OSError, 'simulated'):
                target.apply_live(self.steam, 111, preview['plan_token'], target.CONFIRM)
        self.assertEqual(tuple(p.read_bytes() for p in self.steam.paths), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)

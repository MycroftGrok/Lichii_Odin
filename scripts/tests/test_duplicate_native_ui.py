#!/usr/bin/env python3
"""Simulated duplicate-manager validation. Never reads or writes real Steam files."""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path.home() / 'Applications/Lichii/source'
MODULE = ROOT / 'scripts/steam_duplicate_manager.py'
SOURCE = ROOT / 'src/yuzu/main_window.cpp'
sys.path.insert(0, str(MODULE.parent))
import steam_duplicate_manager as mgr

class NativeDuplicateTests(unittest.TestCase):
    def test_keeper_preview_uses_exact_rom_and_only_owned_entries(self):
        rom = '/games/Dragon Quest I and II.nsp'
        entries = [
            {'appid': 101, 'name': 'Original', 'rom': rom, 'ours': True},
            {'appid': 102, 'name': 'Duplicate', 'rom': rom, 'ours': True},
            {'appid': 103, 'name': 'Other game', 'rom': '/games/Other.nsp', 'ours': True},
            {'appid': 104, 'name': 'Unmanaged', 'rom': rom, 'ours': False},
        ]
        steam = Mock()
        steam.owned.side_effect = lambda e: e['ours']
        steam.get_path.side_effect = lambda e: e['rom']
        with tempfile.TemporaryDirectory() as temp:
            report = mgr.build_report(entries, steam, Path(temp), {
                '101': ['Switch'], '102': ['Favorites', 'Switch']
            })
            self.assertEqual(len(report), 1)
            self.assertEqual(len(report[0]['shortcuts']), 2)
            plan = mgr.preview(report, 101)
            self.assertEqual(plan['keep']['appid'], 101)
            self.assertEqual([x['appid'] for x in plan['would_remove']], [102])
            self.assertEqual(plan['collection_names_to_review'], ['Favorites', 'Switch'])
            self.assertEqual(len(plan['missing_artwork_on_keeper']), 5)
            with self.assertRaises(ValueError):
                mgr.preview(report, 103)

    def test_qt_chooser_is_read_only(self):
        s = SOURCE.read_text(encoding='utf-8')
        self.assertIn('LICHII_DUPLICATE_CHOOSER_V1', s)
        self.assertIn('steam_duplicate_manager.py', s)
        self.assertIn('Manage duplicate Lichii shortcuts', s)
        self.assertIn('LICHII_DUPLICATE_GUARDED_APPLY_V1', s)
        self.assertIn('REMOVE-ONLY-SELECTED', s)
        self.assertIn('QComboBox', s)
        self.assertIn('--preview-keep-appid', s)
        self.assertNotIn('duplicate --apply', s)

if __name__ == '__main__':
    unittest.main(verbosity=2)

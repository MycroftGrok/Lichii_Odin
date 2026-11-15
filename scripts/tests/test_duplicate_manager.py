from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import steam_duplicate_manager as mgr

class DuplicateTests(unittest.TestCase):
    def test_only_identical_roms_and_owned_shortcuts(self):
        a = {'appid': -2, 'name': 'A', 'rom': '/games/a.nsp', 'owned': True}
        b = {'appid': -3, 'name': 'B', 'rom': '/games/a.nsp', 'owned': True}
        c = {'appid': -4, 'name': 'C', 'rom': '/games/a.nsp', 'owned': False}
        d = {'appid': -5, 'name': 'D', 'rom': '/games/d.nsp', 'owned': True}
        api = Mock()
        api.owned.side_effect = lambda e: e['owned']
        api.get_path.side_effect = lambda e: e['rom']
        groups = mgr.duplicate_groups([a, b, c, d], api)
        self.assertEqual(list(groups), ['/games/a.nsp'])
        self.assertEqual(len(groups['/games/a.nsp']), 2)
        with tempfile.TemporaryDirectory() as tmp:
            report = mgr.build_report([a, b, c, d], api, Path(tmp))
            plan = mgr.preview(report, (-2) & 0xffffffff)
            self.assertEqual(len(plan['would_remove']), 1)
            self.assertEqual(plan['keep']['appid'], (-2) & 0xffffffff)
            with self.assertRaises(ValueError):
                mgr.preview(report, 12)

    def test_no_duplicates(self):
        api = Mock()
        api.owned.return_value = True
        api.get_path.return_value = '/games/a.nsp'
        self.assertEqual(mgr.duplicate_groups([{'appid': 1}], api), {})

if __name__ == '__main__':
    unittest.main(verbosity=2)

"""Synthetic safety tests; never access or modify actual Steam userdata."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / 'steam_artwork_manual.py'
if not MODULE_PATH.is_file():
    MODULE_PATH = Path(__file__).with_name('steam_artwork_manual.py')
spec = importlib.util.spec_from_file_location('steam_artwork_manual_tested', MODULE_PATH)
manual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manual)


class FakeArt:
    ARTWORK_TYPES = (
        ('portrait cover','grids','600x900','p'),
        ('landscape cover','grids','920x430',''),
        ('hero background','heroes',None,'_hero'),
        ('transparent logo','logos',None,'_logo'),
        ('icon','icons',None,'_icon'),
    )
    def search_title(self, title):
        return title
    def existing_art(self, grid, appid, suffix):
        return (grid / f'{appid}{suffix}.png').is_file()
    def request_json(self, path, key):
        if path.startswith('/search/'):
            return [{'id':41,'name':'Metroid II','release_date':946684800},
                    {'id':42,'name':'AM2R','release_date':None}]
        return [{'url':'https://cdn2.steamgriddb.com/image.png'}]
    def load_image(self, url, kind):
        if not url.startswith('https://cdn2.steamgriddb.com/'):
            raise ValueError('outside CDN')
        return b'PNG-image-bytes', '.png'
    def save_art(self, grid, filename, data):
        p=grid/filename
        if not p.exists():
            p.write_bytes(data)


class ManualTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.grid = self.root/'config/grid'
        self.grid.mkdir(parents=True)
        self.entries = {
            101:{'appid':101,'title':'AM2R','rom':'/roms/AM2R.nsp','user':self.root},
            202:{'appid':202,'title':'Fully Covered','rom':'/roms/Covered.nsp','user':self.root},
            303:{'appid':303,'title':'Partly Covered','rom':'/roms/Partial.nsp','user':self.root},
        }
        self.art = FakeArt()
        for _,_,_,suffix in self.art.ARTWORK_TYPES:
            (self.grid/f'202{suffix}.png').write_bytes(b'existing')
        (self.grid/'303p.png').write_bytes(b'existing')

    def test_queue_only_when_all_artwork_missing(self):
        previous = manual.library
        manual.library=lambda steam: self.entries
        try:
            rows = manual.fallback_queue(object(), self.art)
            self.assertEqual([r['appid'] for r in rows], [101])
        finally:
            manual.library=previous

    def test_queue_only_latest_completed_scrape(self):
        previous = manual.library
        manual.library=lambda steam: self.entries
        try:
            log=self.root/'latest.log'
            log.write_text('Action: artwork\nARTWORK: AM2R\nResult: finished\n')
            self.assertEqual(len(manual.fallback_queue(None,self.art,True,log)),1)
            log.write_text('Action: artwork\nARTWORK: AM2R\nResult: failed or interrupted\n')
            self.assertEqual(manual.fallback_queue(None,self.art,True,log),[])
            log.write_text('Action: artwork\nARTWORK: Fully Covered\nResult: finished\n')
            self.assertEqual(manual.fallback_queue(None,self.art,True,log),[])
        finally:
            manual.library=previous

    def test_manual_search_accepts_nonexact_candidates(self):
        got=manual.candidates(self.art,'metroid', 'dummy')
        self.assertEqual([g['id'] for g in got], [41,42])
        manual.confirm_candidate(self.art,'metroid',42,'dummy')
        with self.assertRaises(RuntimeError):
            manual.confirm_candidate(self.art,'metroid',99,'dummy')
        with self.assertRaises(ValueError):
            manual.validate_query('x')

    def test_installs_missing_art_only_and_preserves_existing(self):
        got,issues=manual.install_missing(self.art,self.grid,303,41,'dummy')
        self.assertEqual(got,4)
        self.assertEqual((self.grid/'303p.png').read_bytes(),b'existing')
        self.assertEqual(len(manual.missing_types(self.art,self.grid,303)),0)
        self.assertEqual(issues,[])

    def test_no_unrelated_shortcut_files_touched(self):
        sentinel=self.root/'config/shortcuts.vdf'
        sentinel.write_bytes(b'untouched')
        got,_=manual.install_missing(self.art,self.grid,101,41,'dummy')
        self.assertEqual(got,5)
        self.assertEqual(sentinel.read_bytes(),b'untouched')


if __name__=='__main__':
    unittest.main(verbosity=2)

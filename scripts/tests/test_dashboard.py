from pathlib import Path
import importlib.util
spec=importlib.util.spec_from_file_location('dashboard',Path(__file__).resolve().parents[1] / 'steam_dashboard.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
example='''Lichii Steam Integration
Action: artwork
Started: 2026-11-11T14:38:14-05:00
ARTWORK: AM2R
  No exact SteamGridDB match: AM2R
ARTWORK: Dragon Quest III
  portrait cover: installed
  landscape cover: installed
  hero background: installed
  transparent logo: installed
  icon: installed
ARTWORK: Legend of Mana
  Ambiguous SteamGridDB matches (2): Legend of Mana
Artwork summary: 5 installed; 10 missing/unmatched assets.
Updated 1 Steam shortcut icon paths; backup: /tmp/dummy
Result: finished
Finished: 2026-11-11T14:38:17-05:00
'''
a=d.parse(example)
assert a['games_detected']==3,a
assert a['games_updated']==1,a
assert a['games_missing_artwork']==2,a
assert a['artwork_files_installed']==5,a
assert a['missing_artwork_files']==10,a
assert a['errors']==0,a
print('PASS: completion statistics parser')

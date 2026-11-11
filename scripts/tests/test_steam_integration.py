#!/usr/bin/env python3
"""Offline regression tests: no real Steam installation or ROM data involved."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from argparse import Namespace

SCRIPT = Path(__file__).resolve().parents[1] / "steam-integration.py"
spec = importlib.util.spec_from_file_location("lichii_steam", SCRIPT)
steam = importlib.util.module_from_spec(spec)
spec.loader.exec_module(steam)


class SteamIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        home = Path(self.temp.name)
        steam.HOME = home
        steam.SCRIPT = home / ".local/bin/lichii-steam-game"
        steam.LAUNCHER = home / ".local/bin/lichii-odin"
        steam.PROFILES = [home / ".config/lichii/qt-config.ini"]
        steam.ROOTS = [home / "Games"]
        steam.STEAM_ROOTS = [home / ".local/share/Steam"]
        steam.BACKUPS = home / ".local/share/lichii/backups"
        steam.steam_running = lambda: False
        steam.SCRIPT.parent.mkdir(parents=True)
        steam.SCRIPT.write_text("#!/usr/bin/env bash\n")
        steam.LAUNCHER.write_text("#!/usr/bin/env bash\n")
        self.root = home / "Games"
        self.rom1 = self.root / "Switch" / "Example One.nsp"
        self.rom2 = self.root / "Switch 2" / "Example Two.nup"
        self.rom1.parent.mkdir(parents=True)
        self.rom2.parent.mkdir(parents=True)
        self.rom1.write_bytes(b"rom placeholder")
        self.rom2.write_bytes(b"rom placeholder")
        user = home / ".local/share/Steam/userdata/1234"
        config = user / "config"
        config.mkdir(parents=True)
        cloud = config / "cloudstorage"
        cloud.mkdir()
        self.shortcuts = config / "shortcuts.vdf"
        self.collections = cloud / "cloud-storage-namespace-1.json"
        self.namespace = cloud / "cloud-storage-namespaces.json"
        self.collections.write_text(json.dumps([
            ["user-collections.uc-existing",
             {"key": "user-collections.uc-existing",
              "timestamp": 1, "version": "1",
              "value": json.dumps({"id": "uc-existing",
                                   "name": "Unrelated",
                                   "added": [1234], "removed": []})}]
        ]))
        self.namespace.write_text('[[1,"100"]]')
        # Preserve an unrelated Steam shortcut byte-for-byte across changes.
        other = (b"\x000\x00" + steam.vint("appid", 1234) +
                 steam.vstring("AppName", "Unrelated") +
                 steam.vstring("Exe", '"/bin/true"') +
                 steam.vstring("LaunchOptions", "") + b"\x00tags\x00\x08\x08")
        self.shortcuts.write_bytes(b"\x00shortcuts\x00" + other + b"\x08\x08")
        self.original = self.shortcuts.read_bytes()

    @staticmethod
    def run_mode(mode):
        steam.do_import(Namespace(mode=mode, rom_root=[], dry_run=False, yes=True,
                                       no_artwork=True, configure_artwork=False))

    def test_import_deduplicate_and_clear(self):
        self.run_mode("all")
        blob, entries, _, _ = steam.read_shortcuts(self.shortcuts.read_bytes())
        self.assertEqual(len(entries), 3)
        groups = {json.loads(e[1]["value"])["name"]: json.loads(e[1]["value"])
                  for e in json.loads(self.collections.read_text())
                  if e[0].startswith("user-collections.")}
        self.assertEqual(len(groups["Switch"]["added"]), 1)
        self.assertEqual(len(groups["Switch 2"]["added"]), 1)
        self.assertEqual(groups["Unrelated"]["added"], [1234])
        before = (self.shortcuts.read_bytes(), self.collections.read_bytes(),
                  self.namespace.read_bytes())
        self.run_mode("all")
        self.assertEqual((self.shortcuts.read_bytes(), self.collections.read_bytes(),
                          self.namespace.read_bytes()), before)
        self.run_mode("clear")
        blob, entries, _, _ = steam.read_shortcuts(self.shortcuts.read_bytes())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "Unrelated")
        groups = {json.loads(e[1]["value"])["name"]: json.loads(e[1]["value"])
                  for e in json.loads(self.collections.read_text())
                  if e[0].startswith("user-collections.")}
        self.assertEqual(groups["Switch"]["added"], [])
        self.assertEqual(groups["Switch 2"]["added"], [])
        self.assertEqual(groups["Unrelated"]["added"], [1234])
        self.assertTrue(any(steam.BACKUPS.iterdir()))

    def test_mode_switch_only(self):
        self.run_mode("switch")
        _, entries, _, _ = steam.read_shortcuts(self.shortcuts.read_bytes())
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[1]["name"], "Example One")
        self.run_mode("switch2")
        _, entries, _, _ = steam.read_shortcuts(self.shortcuts.read_bytes())
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[2]["name"], "Example Two")

    def test_configured_gamedirs(self):
        extra = steam.HOME / "Extra Games"
        extra.mkdir()
        config = steam.PROFILES[0]
        config.parent.mkdir(parents=True)
        config.write_text("[UI]\ngamedirs\\1\\path=" + str(extra) + "\n")
        self.assertIn(extra.resolve(), steam.scan_roots([]))


if __name__ == "__main__":
    unittest.main()

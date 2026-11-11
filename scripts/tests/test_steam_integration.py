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

    def test_fill_blank_steam_icon_only(self):
        self.run_mode("switch")
        _, entries, _, _ = steam.read_shortcuts(self.shortcuts.read_bytes())
        appid = entries[1]["appid"] & 0xffffffff
        grid = self.shortcuts.parent / "grid"
        grid.mkdir()
        icon = grid / f"{appid}_icon.png"
        icon.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
        steam.set_shortcut_icons(self.shortcuts.parent.parent)
        after = self.shortcuts.read_bytes()
        self.assertIn(str(icon).encode(), after)
        self.assertTrue(any(steam.BACKUPS.iterdir()))
        steam.set_shortcut_icons(self.shortcuts.parent.parent)
        self.assertEqual(after, self.shortcuts.read_bytes())

    def test_mode_switch_only(self):
        self.run_mode("switch")
        _, entries, _, _ = steam.read_shortcuts(self.shortcuts.read_bytes())
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[1]["name"], "Example One")
        self.run_mode("switch2")
        _, entries, _, _ = steam.read_shortcuts(self.shortcuts.read_bytes())
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[2]["name"], "Example Two")

    def test_shell_safe_rom_paths(self):
        import shlex
        rom = self.root / "Switch" / "Example $(touch BAD) [USA];.nsp"
        rom.write_bytes(b"placeholder")
        appid = 0x80000420
        sample = (b"\x00shortcuts\x00" +
                  steam.make_shortcut(0, appid, "Special game", rom) + b"\x08\x08")
        _, entries, _, _ = steam.read_shortcuts(sample)
        self.assertEqual(len(entries), 1)
        self.assertTrue(steam.owned(entries[0]))
        self.assertEqual(shlex.split(entries[0]["options"]), [str(rom)])
        self.assertEqual(steam.get_path(entries[0]), str(rom.resolve()))

    def test_display_names_remove_dump_metadata(self):
        first = Path("/roms/Switch 2/The Legend of Zelda Ocarina of Time "
                     "[0400486024DEC000][v131072].nup")
        self.assertEqual(steam.game_display_name(first),
                         "The Legend of Zelda Ocarina of Time")
        second = Path("/roms/Switch/Diablo III Eternal Collection "
                      "[Diablo III Blizzard's 30th Anniversary Bundle] "
                      "[01001B300B9BF064] [PE] [v0].xci")
        self.assertEqual(steam.game_display_name(second),
                         "Diablo III Eternal Collection "
                         "[Diablo III Blizzard's 30th Anniversary Bundle] [PE]")

    def test_exclude_dlc_updates_and_keep_full_games(self):
        examples = [
            "Mario Kart 8 Deluxe - Wave 1-6 (World) (DLC Unlocker) (eShop).nsp",
            "[DLC] TLoZ BotW DLC Pack 1.nsp",
            "v-dragon quest i and ii hd 2d remake adventurous accessory kit dlc.nsp",
            "The Game Update [v131072].nsp",
        ]
        for name in examples:
            rom = self.root / "Switch" / name
            rom.write_bytes(b"addon placeholder")
            self.assertIsNotNone(steam.non_game_package_reason(rom))
        full_game = self.root / "Switch" / (
            "Diablo III Eternal Collection [01001B300B9BF064] [PE] [v0].xci"
        )
        full_game.write_bytes(b"full game placeholder")
        self.assertIsNone(steam.non_game_package_reason(full_game))
        self.assertIsNone(steam.non_game_package_reason(self.rom2))
        self.run_mode("all")
        _, entries, _, _ = steam.read_shortcuts(self.shortcuts.read_bytes())
        self.assertEqual(len(entries), 4)  # unrelated + 3 playable games
        self.assertTrue(all("DLC" not in e["name"].upper() for e in entries))

    def test_configured_gamedirs(self):
        extra = steam.HOME / "Extra Games"
        extra.mkdir()
        config = steam.PROFILES[0]
        config.parent.mkdir(parents=True)
        config.write_text("[Paths]\ngamedirs\\1\\path=" + str(extra) + "\n")
        self.assertIn(extra.resolve(), steam.scan_roots([]))

    def test_armadaos_paths_gamedirs_and_sibling_switch_folder(self):
        card = steam.HOME / "AndroidCard" / "roms"
        switch2 = card / "Switch 2"
        switch1 = card / "Switch"
        switch2.mkdir(parents=True)
        switch1.mkdir()
        config = steam.PROFILES[0]
        config.parent.mkdir(parents=True)
        config.write_text(
            "[General]\n"
            "Paths\\gamedirs\\size=4\n"
            "Paths\\gamedirs\\4\\path=" + str(switch2) + "\n"
            "Paths\\recentFiles=" + str(switch2 / "Zelda [123456789ABCDEF0].nup") + "\n"
        )
        found = steam.scan_roots([])
        self.assertIn(switch2.resolve(), found)
        self.assertIn(switch1.resolve(), found)


if __name__ == "__main__":
    unittest.main()

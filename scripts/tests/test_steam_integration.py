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
        steam.STEAM_ROOTS = [home / ".local/share/Steam"]
        steam.BACKUPS = home / ".local/share/lichii/backups"
        steam.LATEST_LOG = home / ".local/share/lichii/logs/steam-integration-latest.log"
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
        config_file = steam.PROFILES[0]
        config_file.parent.mkdir(parents=True)
        config_file.write_text(
            "[Paths]\n"
            "Paths\\gamedirs\\size=2\n"
            "Paths\\gamedirs\\1\\path=" + str(self.rom1.parent) + "\n"
            "Paths\\gamedirs\\1\\deep_scan=false\n"
            "Paths\\gamedirs\\2\\path=" + str(self.rom2.parent) + "\n"
            "Paths\\gamedirs\\2\\deep_scan=false\n"
        )
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

    def test_latest_log_captures_stdout_stderr_and_finished_status(self):
        import sys
        print("Before log")
        with steam.record_latest_log("artwork"):
            print("ARTWORK: Example Game")
            print("portrait cover: not available", file=sys.stderr)
        path = steam.LATEST_LOG
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        result = path.read_text()
        self.assertIn("Action: artwork", result)
        self.assertIn("ARTWORK: Example Game", result)
        self.assertIn("portrait cover: not available", result)
        self.assertIn("Result: finished", result)
        self.assertNotIn("Before log", result)

    def test_latest_log_updates_even_if_action_fails(self):
        import sys
        with steam.record_latest_log("switch"):
            print("OLD RESULT")
        with self.assertRaisesRegex(RuntimeError, "Steam not closed"):
            with steam.record_latest_log("artwork"):
                print("ERROR: Steam not closed", file=sys.stderr)
                raise RuntimeError("Steam not closed")
        result = steam.LATEST_LOG.read_text()
        self.assertNotIn("OLD RESULT", result)
        self.assertIn("ERROR: Steam not closed", result)
        self.assertIn("Result: failed or interrupted", result)
        self.assertIn("Finished:", result)

    def test_latest_log_rejects_symlink_without_overwriting_target(self):
        original = Path(self.temp.name) / "external.log"
        original.write_text("untouched")
        steam.LATEST_LOG.parent.mkdir(parents=True)
        steam.LATEST_LOG.symlink_to(original)
        with self.assertRaisesRegex(RuntimeError, "symbolic-link Steam log"):
            with steam.record_latest_log("artwork"):
                print("This should not be logged")
        self.assertEqual(original.read_text(), "untouched")

    def test_steam_process_detection_current_user_ignores_zombies(self):
        from unittest.mock import patch
        sample = (
            " 50 Ss steam\n"
            " 51 Sl steamwebhelper\n"
            " 52 Z steam\n"
            " 53 Ss unrelated\n"
            " 54 Sl steam-runtime-l\n"
        )
        with patch.object(steam.subprocess, "check_output", return_value=sample) as ps:
            processes = steam.steam_processes()
        self.assertEqual(processes, [
            (50, "steam"), (51, "steamwebhelper"), (54, "steam-runtime-l")
        ])
        args = ps.call_args.args[0]
        self.assertEqual(args[:2], ["ps", "-u"])
        self.assertNotIn("-eo", args)

    def test_active_steam_without_shutdown_consent_aborts(self):
        from unittest.mock import patch
        with patch.object(steam, "steam_running", return_value=True), \
             patch.object(steam, "steam_processes",
                          return_value=[(123, "steamwebhelper")]):
            with self.assertRaisesRegex(RuntimeError, "Steam is still active"):
                steam.ensure_steam_closed(Namespace(shutdown_steam=False))

    def test_shutdown_consent_calls_graceful_shutdown(self):
        from unittest.mock import patch
        with patch.object(steam, "steam_running", side_effect=[True, False]), \
             patch.object(steam, "close_steam_gracefully") as shutdown:
            steam.ensure_steam_closed(Namespace(shutdown_steam=True))
            shutdown.assert_called_once_with()

    def test_native_steam_shutdown_success_never_uses_signals(self):
        from unittest.mock import patch
        from subprocess import CompletedProcess
        with patch.object(steam, "steam_processes",
                          side_effect=[[(123, "steam")], []]), \
             patch.object(steam.shutil, "which", return_value="/usr/bin/steam"), \
             patch.object(steam.subprocess, "run",
                          return_value=CompletedProcess(["steam", "-shutdown"], 0)) as run, \
             patch.object(steam.os, "kill") as kill:
            steam.close_steam_gracefully()
            self.assertEqual(run.call_args.args[0], ["/usr/bin/steam", "-shutdown"])
            kill.assert_not_called()

    def test_steam_shutdown_without_launcher_uses_sigterm_only(self):
        from unittest.mock import patch
        import signal
        with patch.object(steam, "steam_processes",
                          side_effect=[[(123, "steamwebhelper")],
                                       [(123, "steamwebhelper")], []]), \
             patch.object(steam.shutil, "which", return_value=None), \
             patch.object(steam.os, "kill") as kill:
            steam.close_steam_gracefully()
            kill.assert_called_once_with(123, signal.SIGTERM)

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

    def test_configured_gamedirs_only(self):
        extra = steam.HOME / "Extra Games"
        extra.mkdir()
        config = steam.PROFILES[0]
        config.write_text("[Paths]\nPaths\\gamedirs\\1\\path=" + str(extra) + "\n")
        self.assertEqual(steam.scan_roots([]), [(extra.resolve(), False)])

    def test_armadaos_config_does_not_add_unregistered_sibling_or_recent_path(self):
        card = steam.HOME / "AndroidCard" / "roms"
        switch2 = card / "Switch 2"
        switch1 = card / "Switch"
        recent = card / "Other"
        switch2.mkdir(parents=True)
        switch1.mkdir()
        recent.mkdir()
        config = steam.PROFILES[0]
        config.write_text(
            "[General]\n"
            "Paths\\gamedirs\\size=4\n"
            "Paths\\gamedirs\\4\\path=" + str(switch2) + "\n"
            "Paths\\gamedirs\\4\\deep_scan=false\n"
            "Paths\\recentFiles=" + str(recent / "Other Game.nup") + "\n"
        )
        roots = steam.scan_roots([])
        self.assertEqual(roots, [(switch2.resolve(), False)])
        self.assertNotIn((switch1.resolve(), False), roots)
        self.assertNotIn((recent.resolve(), False), roots)

    def test_root_override_rejected(self):
        from unittest.mock import patch
        with self.assertRaisesRegex(RuntimeError, "add that directory to Lichii"):
            steam.scan_roots([str(self.rom1.parent)])
        other = steam.HOME / ".config/eden/qt-config.ini"
        other.parent.mkdir(parents=True)
        other.write_text(
            "[General]\nPaths\\gamedirs\\1\\path="
            + str(self.rom2.parent) + "\n"
        )
        steam.PROFILES = [steam.HOME / "missing-lichii.ini"]
        with self.assertRaisesRegex(RuntimeError, "No Lichii qt-config.ini"):
            steam.scan_roots([])

    def test_obey_deep_scan_setting_and_ignore_outside_symlinks(self):
        library = self.root / "Switch 2"
        nested = library / "Nested"
        nested.mkdir()
        nested_rom = nested / "Nested Game.nup"
        nested_rom.write_bytes(b"rom placeholder")
        bad_link = library / "Outside Game.nup"
        outsider = steam.HOME / "Outside Game.nup"
        outsider.write_bytes(b"rom placeholder")
        bad_link.symlink_to(outsider)
        config = steam.PROFILES[0]
        config.write_text(
            "[General]\n"
            "Paths\\gamedirs\\1\\path=" + str(library) + "\n"
            "Paths\\gamedirs\\1\\deep_scan=false\n"
        )
        roots = steam.scan_roots([])
        self.assertEqual(steam.roms_in(roots), [self.rom2.resolve()])
        config.write_text(config.read_text().replace(
            "deep_scan=false", "deep_scan=true"
        ))
        self.assertEqual(
            steam.roms_in(steam.scan_roots([])),
            sorted([nested_rom.resolve(), self.rom2.resolve()]),
        )

    def test_artwork_scans_only_games_still_in_lichii(self):
        from unittest.mock import patch
        self.run_mode("all")
        config = steam.PROFILES[0]
        config.write_text(
            "[Paths]\nPaths\\gamedirs\\4\\path="
            + str(self.rom2.parent) + "\n"
            "Paths\\gamedirs\\4\\deep_scan=false\n"
        )
        with patch.object(steam, "scrape_apps") as scrape:
            steam.do_import(Namespace(
                mode="artwork", rom_root=[], dry_run=False, yes=True,
                no_artwork=False, shutdown_steam=False
            ))
            scrape.assert_called_once()
            items = scrape.call_args.args[1]
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0][1], "Example Two")

    def test_import_scans_only_lichii_registered_game_folder(self):
        config = steam.PROFILES[0]
        config.write_text(
            "[Paths]\nPaths\\gamedirs\\4\\path="
            + str(self.rom2.parent) + "\n"
            "Paths\\gamedirs\\4\\deep_scan=false\n"
        )
        self.run_mode("all")
        _, entries, _, _ = steam.read_shortcuts(self.shortcuts.read_bytes())
        self.assertEqual([e["name"] for e in entries],
                         ["Unrelated", "Example Two"])


if __name__ == "__main__":
    unittest.main()

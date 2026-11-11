#!/usr/bin/env python3
"""Offline SteamGridDB scraper tests. Never call the network."""
import importlib.util
from pathlib import Path
import tempfile
from unittest import mock
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "steam_artwork.py"
spec = importlib.util.spec_from_file_location("steam_artwork_test", SOURCE)
art = importlib.util.module_from_spec(spec)
spec.loader.exec_module(art)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class ArtTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.grid = Path(self.temp.name) / "userdata/1234/config/grid"

    def test_filename_and_exact_match(self):
        self.assertEqual(art.normalized("Example Game [USA]"), "examplegame")
        self.assertEqual(art.normalized("Example Game"), "examplegame")
        with mock.patch.object(art, "request_json", return_value=[
            {"id": 42, "name": "Example Game"},
            {"id": 41, "name": "Completely different game"}
        ]):
            self.assertEqual(art.lookup_game_id("Example Game", "fake-key"), 42)
        with mock.patch.object(art, "request_json", return_value=[
            {"id": 42, "name": "Example Game"},
            {"id": 43, "name": "Example Game"}
        ]):
            self.assertIsNone(art.lookup_game_id("Example Game", "fake-key"))

    def test_nintendo_title_id_selects_correct_version(self):
        # The 2026 Switch 2 game's Nintendo Title ID maps to its distinct
        # SteamGridDB listing, not the identically named 1998 original.
        title = "The Legend of Zelda Ocarina of Time"
        matches = [
            {"id": 21202, "name": "The Legend of Zelda: Ocarina of Time",
             "release_date": 893980800},
            {"id": 5532594, "name": "The Legend of Zelda: Ocarina of Time",
             "release_date": 1793491200},
        ]
        rom = ("/run/media/deck/AndroidCard/roms/Switch 2/"
               "The Legend of Zelda Ocarina of Time [0400486024DEC000][v131072].nup")
        self.assertEqual(art.title_id_from_rom(rom), "0400486024DEC000")
        self.assertIsNone(art.title_id_from_rom("/roms/No ID.nsp"))
        with mock.patch.object(art, "request_json", return_value=matches):
            self.assertEqual(art.lookup_game_id(
                title, "fake", appid=2345,
                title_id=art.title_id_from_rom(rom)), 5532594)
            self.assertIsNone(art.lookup_game_id(
                title, "fake", appid=2345, title_id="0400AAAABBBBCCCC"))

    def test_title_id_choice_persisted_for_unknown_id(self):
        matches = [
            {"id": 81, "name": "Example Game"},
            {"id": 82, "name": "Example Game"},
        ]
        with mock.patch.object(art, "MATCH_FILE",
                               Path(self.temp.name) / "game-matches.json"), \
             mock.patch.object(art, "request_json", return_value=matches):
            art.set_game_match(2345, "Example Game", 82, "fake",
                               title_id="0100AAAABBBBCCCC")
            self.assertEqual(art.lookup_game_id(
                "Example Game", "fake", appid=9999,
                title_id="0100AAAABBBBCCCC"), 82)
            self.assertIsNone(art.lookup_game_id(
                "Other Game", "fake", appid=9999,
                title_id="0100AAAABBBBCCCC"))
            self.assertEqual(art.MATCH_FILE.stat().st_mode & 0o777, 0o600)

    def test_image_files_and_no_overwrite(self):
        def fake_json(path, key):
            if path.startswith("/search/autocomplete/"):
                return [{"id": 42, "name": "Example Game"}]
            return [{"url": "https://cdn2.steamgriddb.com/grid/fake.png", "type": "static"}]
        with mock.patch.object(art, "request_json", side_effect=fake_json), \
             mock.patch.object(art, "load_image", return_value=(PNG, ".png")):
            installed, missing = art.scrape_one(self.grid, 2147483699, "Example Game", "fake")
            self.assertEqual((installed, missing), (5, 0))
            expected = [
                "2147483699p.png", "2147483699.png",
                "2147483699_hero.png", "2147483699_logo.png",
                "2147483699_icon.png"
            ]
            for name in expected:
                self.assertEqual((self.grid / name).read_bytes(), PNG)
            with mock.patch.object(art, "request_json", side_effect=AssertionError("network should not be called")):
                self.assertEqual(art.scrape_one(self.grid, 2147483699,
                                                "Example Game", "fake"), (0, 0))
            self.assertEqual((self.grid / expected[0]).read_bytes(), PNG)

    def test_reject_external_cdn_and_bad_images(self):
        with self.assertRaises(ValueError):
            art.load_image("https://evil.example.org/grid/art.png", "grids")
        self.assertIsNone(art.image_extension(b"<svg/>", "logos"))
        self.assertIsNone(art.image_extension(b"RIFFfakeWEBP", "grids"))
        self.assertEqual(art.image_extension(b"\x00\x00\x01\x00abc", "icon"), ".ico")

    def test_absent_api_key_nonfatal(self):
        with mock.patch.object(art, "token", return_value=None), \
             mock.patch.object(art, "request_json", side_effect=AssertionError("no network")):
            art.apply_artwork(self.grid, [(2345678901, "Missing Key Game")])
            self.assertFalse(self.grid.exists())


if __name__ == "__main__":
    unittest.main()

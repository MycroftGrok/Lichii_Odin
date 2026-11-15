# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract checks for the checked-in handheld catalog (no device required)."""
import json
import re
import unittest
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[2] / "src/yuzu/handheld_catalog.json"
SAFE_ID = re.compile(r"^[a-z0-9-]+$")


class CatalogIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_version(self):
        self.assertEqual(self.data["schema_version"], 1)

    def test_chipset_handheld_model_key_uniqueness(self):
        chipsets, families, models = set(), set(), set()
        for chip in self.data["chipsets"]:
            self.assertRegex(chip["id"], SAFE_ID)
            self.assertNotIn(chip["id"], chipsets)
            chipsets.add(chip["id"])
            self.assertTrue(chip["name"].startswith("Qualcomm Snapdragon"))
            for handheld in chip["handhelds"]:
                self.assertRegex(handheld["id"], SAFE_ID)
                self.assertNotIn(handheld["id"], families)
                families.add(handheld["id"])
                self.assertTrue(handheld["aliases"])
                self.assertGreaterEqual(min(map(len, handheld["aliases"])), 6)
                self.assertTrue(handheld["models"])
                self.assertEqual(handheld["default_settings"], {})
                for model in handheld["models"]:
                    key = handheld["id"] + "-" + model["id"]
                    self.assertRegex(key, SAFE_ID)
                    self.assertNotIn(key, models)
                    models.add(key)
                    self.assertGreater(model["ram_gib"], 0)
        self.assertGreaterEqual(len(chipsets), 3)
        self.assertGreaterEqual(len(models), 18)

    def test_odin_3_ultra_present(self):
        for chip in self.data["chipsets"]:
            for handheld in chip["handhelds"]:
                if handheld["id"] == "ayn-odin-3":
                    self.assertEqual(chip["id"], "snapdragon-8-elite")
                    ultra = [m for m in handheld["models"] if m["id"] == "ultra"]
                    self.assertEqual(len(ultra), 1)
                    self.assertEqual(ultra[0]["ram_gib"], 24)
                    return
        self.fail("Odin 3 Ultra entry missing")


if __name__ == "__main__":
    unittest.main()

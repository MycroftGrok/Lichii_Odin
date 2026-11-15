"""Source-level regressions for selectable Odin controller routing.

Built-in can be Player 1 only (never Player 2). TV multiplayer allows
built-in P1 + external P2 when external priority is unchecked.
Tests do not alter settings, input devices, or controller emulation.
"""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
ROUTING = ROOT / "src/yuzu/controller_routing.cpp"
CONTROLS = ROOT / "src/yuzu/configuration/configure_input.cpp"
UI = ROOT / "src/yuzu/configuration/configure_input.ui"


class BuiltinExclusivePlayer1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routing = ROUTING.read_text(encoding="utf-8")

    def test_preference_defaults_external_and_persists_changes(self):
        self.assertIn(
            'prefs.value(QStringLiteral("prefer_external_player_1"), true).toBool()',
            self.routing,
        )
        self.assertIn(
            'prefs.setValue(QStringLiteral("prefer_external_player_1"), enabled);',
            self.routing,
        )
        self.assertIn("const QString sig = Signature(scan, prefer);", self.routing)

    def test_external_priority_uses_external_player_slots(self):
        self.assertIn("selected = external;", self.routing)
        self.assertIn(
            "const Candidate* p2 = selected.size() > 1 ? selected[1] : nullptr;",
            self.routing,
        )

    def test_builtin_priority_uses_handheld_p1_and_external_p2(self):
        self.assertIn("} else if (!prefer && !built_in.empty()) {", self.routing)
        self.assertIn("selected.push_back(built_in.front());", self.routing)
        self.assertIn(
            "selected.insert(selected.end(), external.begin(), external.end());",
            self.routing,
        )

    def test_built_in_cannot_be_player_two(self):
        self.assertIn("(p2 && p2->built_in)", self.routing)
        self.assertIn(
            "const int index = (built_in_takes_p1 ? 2 : 1) + external_slot++;",
            self.routing,
        )
        self.assertIn("const bool built_in_takes_p1 =", self.routing)

    def test_checkbox_is_enabled_and_saves_preference(self):
        root = ET.parse(UI)
        box = root.find(".//widget[@name='checkPreferExternalPlayer1']")
        self.assertIsNotNone(box)
        self.assertEqual(box.find("./property[@name='checked']/bool").text, "true")
        self.assertEqual(box.find("./property[@name='enabled']/bool").text, "true")
        controls = CONTROLS.read_text(encoding="utf-8")
        self.assertIn(
            "ui->checkPreferExternalPlayer1->setChecked(ControllerRouting::PreferExternal());",
            controls,
        )
        self.assertIn("ui->checkPreferExternalPlayer1->setEnabled(true);", controls)
        self.assertIn(
            "ControllerRouting::SetPreferExternal(ui->checkPreferExternalPlayer1->isChecked());",
            controls,
        )

    def test_idle_routing_reason_is_exposed_in_diagnostics(self):
        self.assertIn('out[QStringLiteral("last_routing_result")]', self.routing)
        self.assertIn('QStringLiteral("Last routing check: ")', self.routing)
        self.assertIn('status.setValue(QStringLiteral("last_routing_result"), message)', self.routing)


if __name__ == "__main__":
    unittest.main()

"""Ensure the external-first preference stays in Controls above Console Mode.

Static fixture only: does not launch Lichii or access user controller settings.
"""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "src/yuzu/configuration/configure_input.ui"
CONTROLS_CPP = ROOT / "src/yuzu/configuration/configure_input.cpp"
MAIN_CPP = ROOT / "src/yuzu/main_window.cpp"


class ControlsPriorityUITests(unittest.TestCase):
    def test_external_priority_above_bottom_left_console_mode(self):
        doc = ET.parse(UI)
        footer = doc.find(
            ".//widget[@name='consoleInputSettings']/"
            "layout[@name='controllerFooterVerticalLayout']"
        )
        self.assertIsNotNone(footer, "Controls footer should use a vertical layout")
        check = footer.find("./item[1]/widget[@name='checkPreferExternalPlayer1']")
        self.assertIsNotNone(check, "Preference should be top-left in footer")
        self.assertEqual(
            check.find("./property[@name='text']/string").text,
            "Prefer external controller for Player 1",
        )
        row = footer.find("./item[2]/layout[@name='buttonsBottomRightHorizontalLayout']")
        self.assertIsNotNone(row, "Existing console footer controls must remain below")
        self.assertIsNotNone(row.find("./item/widget[@name='handheldGroup']"))
        self.assertIsNotNone(
            row.find(".//widget[@name='radioDocked']")
        )
        self.assertIsNotNone(
            row.find(".//widget[@name='radioUndocked']")
        )
        self.assertEqual(len(doc.findall(".//widget[@name='checkPreferExternalPlayer1']")), 1)

    def test_priority_load_apply_and_reset(self):
        c = CONTROLS_CPP.read_text(encoding="utf-8")
        self.assertIn(
            "ui->checkPreferExternalPlayer1->setChecked(ControllerRouting::PreferExternal());",
            c,
        )
        self.assertIn(
            "ui->checkPreferExternalPlayer1->setEnabled(true);",
            c,
        )
        self.assertIn(
            "ControllerRouting::SetPreferExternal(ui->checkPreferExternalPlayer1->isChecked());",
            c,
        )
        self.assertIn(
            "ui->checkPreferExternalPlayer1->setChecked(true);",
            c,
        )

    def test_auto_routing_tracks_real_controller_instead_of_any(self):
        c = (ROOT / "src/yuzu/configuration/configure_input_player.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("player_index >= 2 || !ControllerRouting::AutomaticEnabled()", c)
        self.assertIn("const auto devices = emulated_controller->GetMappedDevices();", c)
        self.assertIn("ui->comboDevices->setCurrentIndex(device_index);", c)

    def test_no_duplicate_diagnostics_checkbox(self):
        c = MAIN_CPP.read_text(encoding="utf-8")
        self.assertNotIn('auto* prefer_external = new QCheckBox(', c)

    def test_preference_explicitly_opts_in_to_automatic_mapping(self):
        r = (ROOT / "src/yuzu/controller_routing.cpp").read_text(encoding="utf-8")
        start = r.split("void SetPreferExternal(bool enabled) {", 1)[1].split("\n}", 1)[0]
        self.assertIn('prefs.setValue(QStringLiteral("automatic_player_assignment"), true);', start)
        self.assertIn('prefs.setValue(QStringLiteral("explicit_takeover"), true);', start)
        c = MAIN_CPP.read_text(encoding="utf-8")
        self.assertIn("previous_external_priority != ControllerRouting::PreferExternal()", c)
        self.assertIn("QApplication::activeModalWidget()", c)

    def test_preview_preserves_prior_opt_in_without_touching_stable(self):
        s = (ROOT / "scripts/resume-hardware-controller-build.sh").read_text(encoding="utf-8")
        self.assertIn('PREVIOUS_RUN="$ROOT/test-runs/$PREVIOUS_NAME"', s)
        self.assertIn('! -name "hardware-controller-fixed-$NOW"', s)
        self.assertIn('"$TESTHOME/.config/lichii/controller-routing.ini"', s)
        self.assertIn('"$PREVIOUS_RUN/config/lichii/qt-config.ini"', s)
        self.assertIn('Stable executable checksum changed.', s)


if __name__ == "__main__":
    unittest.main()

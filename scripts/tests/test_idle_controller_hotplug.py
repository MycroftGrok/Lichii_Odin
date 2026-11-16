"""Source-only guardrails for idle-only SDL3 USB controller hotplug recovery.

These tests never access hardware, input settings, or stable binaries.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
INPUT_H = ROOT / "src/input_common/main.h"
INPUT_CPP = ROOT / "src/input_common/main.cpp"
MAIN = ROOT / "src/yuzu/main_window.cpp"
ROUTING = ROOT / "src/yuzu/controller_routing.cpp"
PATCH = ROOT / ".patch/sdl3/armada-toolbox-idle-hidapi-reprobe.patch"
CPM = ROOT / "cpmfile.json"
SCRIPT = ROOT / "scripts/resume-hardware-controller-build.sh"


class IdleHotplugTests(unittest.TestCase):
    def test_idle_only_router_guards_gameplay_and_modal_editor(self):
        window = MAIN.read_text(encoding="utf-8")
        self.assertIn(
            "if (emulation_running || boot_in_progress || !input_subsystem ||",
            window,
        )
        self.assertIn("QApplication::activeModalWidget()", window)
        self.assertIn("if (ControllerRouting::AutomaticEnabled())", window)
        self.assertIn("input_subsystem->PumpEvents(true);", window)

    def test_regular_input_pumping_is_not_forced_to_rescan(self):
        self.assertIn(
            "void PumpEvents(bool idle_rescan = false) const;",
            INPUT_H.read_text(encoding="utf-8"),
        )
        source = INPUT_CPP.read_text(encoding="utf-8")
        self.assertIn('SDL_SetHint("LICHII_IDLE_HIDAPI_REFRESH", "1");', source)
        self.assertIn('SDL_SetHint("LICHII_IDLE_HIDAPI_REFRESH", "0");', source)
        self.assertIn("SDL_UpdateJoysticks();", source)

    def test_vendor_patch_reproducible_and_checked(self):
        self.assertIn(
            "LICHII_IDLE_HIDAPI_REFRESH", PATCH.read_text(encoding="utf-8")
        )
        self.assertIn(
            "armada-toolbox-idle-hidapi-reprobe.patch",
            CPM.read_text(encoding="utf-8"),
        )
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("SDL3 idle-only HID rescan fallback installed.", script)
        self.assertIn("SDL_HIDAPI=", script)
        self.assertIn("patch --batch --forward", script)

    def test_diagnostics_distinguish_kernel_from_sdl(self):
        source = ROUTING.read_text(encoding="utf-8")
        self.assertIn('QStringLiteral("28DE:1302")', source)
        self.assertIn('QStringLiteral("steam_usb_hid_nodes")', source)
        self.assertIn("USB Steam Controller HID is present but SDL", source)

    def test_qt6_json_append_materializes_qstring(self):
        source = ROUTING.read_text(encoding="utf-8")
        self.assertIn('const QString node = QStringLiteral("/dev/") + entry;', source)
        self.assertIn("steam_usb_nodes.append(node);", source)
        self.assertNotIn('steam_usb_nodes.append(QStringLiteral("/dev/") + entry);', source)

    def test_present_usb_but_missing_sdl_is_not_false_assigned(self):
        source = ROUTING.read_text(encoding="utf-8")
        self.assertIn("if (!steam_visible_in_sdl && !SteamUsbHidNodes().isEmpty())", source)
        self.assertIn("Keeping existing P1/P2 mappings", source)
        self.assertIn("SDL_hid_enumerate(0x28de, 0x1302)", source)
        self.assertIn("SDL_hid_free_enumeration(info)", source)
        self.assertIn("ACTUAL mapped Player 1:", source)
        self.assertIn("ACTUAL mapped Player 2:", source)


if __name__ == "__main__":
    unittest.main()

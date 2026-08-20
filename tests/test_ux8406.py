import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
LIB_PATH = ROOT / "files/hardware/asus-zenbook-duo-ux8406/usr/libexec/current_zenbook_duo_lib.py"
spec = importlib.util.spec_from_file_location("ux8406lib", LIB_PATH)
lib = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lib
spec.loader.exec_module(lib)


PROFILE = ROOT / "files/hardware/asus-zenbook-duo-ux8406/usr/lib/current/zenbook-duo/profiles/UX8406MA.conf"


def state(external=False, missing=False):
    monitors = [
        [["eDP-1", "SDC", "0x419d", "0x00000000"],
         [["2880x1800@120", 2880, 1800, 120.0, 1.0, [1.0], {"is-current": True}]], {}],
        [["eDP-2", "SDC", "0x419d", "0x00000000"],
         [["2880x1800@120", 2880, 1800, 120.0, 1.0, [1.0], {"is-current": True}]], {}],
    ]
    if missing:
        monitors.pop()
    if external:
        monitors.append([["HDMI-1", "DEL", "DELL", "1"], [["1920x1080@60", 1920, 1080, 60.0, 1.0, [1.0], {"is-current": True}]], {}])
    return lib.parse_mutter_state([1, monitors, [], {}])


class UX8406Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = lib._profile(PROFILE)

    def test_known_and_unknown_models(self):
        self.assertIsNotNone(lib.load_profile("ASUSTeK COMPUTER INC.", "UX8406MA", PROFILE.parent))
        self.assertTrue(lib.family_product("UX8406CA"))
        self.assertIsNone(lib.load_profile("ASUSTeK COMPUTER INC.", "UX8406CA", PROFILE.parent))

    def test_external_monitor_protection_and_missing_panel(self):
        self.assertTrue(lib.has_external_monitor(state(True), ("eDP-1", "eDP-2")))
        self.assertFalse(lib.has_external_monitor(state(False), ("eDP-1", "eDP-2")))
        self.assertEqual(lib.layout_plan(state(missing=True), self.profile), [])

    def test_four_layouts_and_mode_selection(self):
        for orientation in ("normal", "bottom-up", "left-up", "right-up"):
            plan = lib.layout_plan(state(), self.profile, orientation)
            self.assertEqual(len(plan), 2)
            self.assertEqual([p["mode"] for p in plan], ["2880x1800@120", "2880x1800@120"])
        self.assertEqual(lib.layout_plan(state(), self.profile, attached=True)[0]["connector"], "eDP-1")

    def test_brightness_normalization(self):
        self.assertEqual(lib.brightness_value(50, 100, 200), 100)
        self.assertEqual(lib.brightness_value(1, 100, 200), 2)
        self.assertEqual(lib.brightness_value(200, 100, 200), 200)

    def test_charge_limit_validation(self):
        self.assertEqual(lib.validate_charge_limit("80"), 80)
        with self.assertRaises(ValueError):
            lib.validate_charge_limit(0)
        with self.assertRaises(ValueError):
            lib.validate_charge_limit(101)

    def test_keyboard_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            usb = Path(directory) / "1-1"
            usb.mkdir()
            (usb / "idVendor").write_text("0b05\n")
            (usb / "idProduct").write_text("1b2c\n")
            self.assertTrue(lib.keyboard_attached(self.profile, Path(directory)))


if __name__ == "__main__":
    unittest.main()

import configparser
import importlib.machinery
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
HARDWARE = ROOT / "files/hardware/asus-zenbook-duo-ux8406"
LIB_PATH = HARDWARE / "usr/libexec/current_zenbook_duo_lib.py"
HELPER_PATH = HARDWARE / "usr/libexec/current-zenbook-duo"
PROFILE = HARDWARE / "usr/lib/current/zenbook-duo/profiles/UX8406MA.conf"


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


lib = load_module("ux8406lib", LIB_PATH)
helper = load_module("ux8406helper", HELPER_PATH)


class UX8406Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = lib._profile(PROFILE)

    def config(self, scale="auto", mode=""):
        parser = configparser.ConfigParser()
        parser.read_dict({"Display": {"Scale": scale, "Mode": mode}})
        return parser

    def test_realistic_ma_dmi_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            dmi = Path(directory)
            (dmi / "sys_vendor").write_text("ASUSTeK COMPUTER INC.\n")
            (dmi / "board_name").write_text("UX8406MA\n")
            (dmi / "product_name").write_text("ASUS Zenbook Duo UX8406MA_UX8406MA\n")
            self.assertTrue(lib.hardware_status(PROFILE.parent, dmi)[0])
            self.assertEqual(lib.load_profile(profile_dir=PROFILE.parent, dmi_root=dmi).name, "UX8406MA")

    def test_product_name_is_only_a_fallback_and_ca_fails_closed(self):
        self.assertEqual(lib.model_key("ASUSTeK COMPUTER INC.", "", "ASUS Zenbook Duo UX8406MA_UX8406MA"), "UX8406MA")
        self.assertEqual(lib.model_key("ASUSTeK COMPUTER INC.", "UX8406CA", "Zenbook Duo"), "UX8406CA")
        self.assertIsNone(lib.load_profile("ASUSTeK COMPUTER INC.", "UX8406CA", "Zenbook Duo", PROFILE.parent))
        self.assertIsNone(lib.model_key("Other", "UX8406MA", "UX8406MA"))
        with tempfile.TemporaryDirectory() as directory:
            dmi = Path(directory)
            (dmi / "sys_vendor").write_text("ASUSTeK COMPUTER INC.\n")
            (dmi / "board_name").write_text("UX8406CA\n")
            (dmi / "product_name").write_text("ASUS Zenbook Duo UX8406CA\n")
            supported, message = lib.hardware_status(PROFILE.parent, dmi)
            self.assertFalse(supported)
            self.assertIn("no UX8406CA profile", message)
        with tempfile.TemporaryDirectory() as directory:
            dmi = Path(directory)
            (dmi / "sys_vendor").write_text("Other vendor\n")
            (dmi / "board_name").write_text("UX8406MA\n")
            (dmi / "product_name").write_text("UX8406MA\n")
            self.assertFalse(lib.hardware_status(PROFILE.parent, dmi)[0])

    def test_top_and_bottom_commands_are_logical_and_at_origin(self):
        top = lib.build_gdctl_command(self.profile, "top", "normal", self.config())
        bottom = lib.build_gdctl_command(self.profile, "bottom", "normal", self.config())
        self.assertEqual(top[:4], ["gdctl", "set", "--layout-mode", "logical"])
        self.assertIn("eDP-1", top)
        self.assertIn("--primary", top)
        self.assertNotIn("--below", top)
        self.assertIn("eDP-2", bottom)
        self.assertIn("--primary", bottom)
        self.assertNotIn("--below", bottom)
        self.assertNotIn("--above", bottom)
        self.assertNotIn("--x", bottom)
        self.assertNotIn("--y", bottom)
        self.assertNotIn("--persistent", bottom)

    def test_both_and_portrait_commands_use_relative_placement(self):
        normal = lib.build_gdctl_command(self.profile, "both", "normal", self.config())
        left = lib.build_gdctl_command(self.profile, "both", "left-up", self.config())
        right = lib.build_gdctl_command(self.profile, "both", "right-up", self.config())
        upside_down = lib.build_gdctl_command(self.profile, "both", "bottom-up", self.config())
        self.assertIn("--below", normal)
        self.assertIn("eDP-1", normal[normal.index("--below") + 1:])
        self.assertIn("90", left)
        self.assertIn("--right-of", left)
        self.assertIn("270", right)
        self.assertIn("--right-of", right)
        self.assertIn("180", upside_down)
        self.assertIn("--above", upside_down)

    def test_scale_defaults_and_administrator_override(self):
        default = lib.build_gdctl_command(self.profile, "both", "normal", self.config())
        override = lib.build_gdctl_command(self.profile, "both", "normal", self.config("2"))
        self.assertIn("1.66667", default)
        self.assertIn("2", override)

    def test_optional_mode_override_is_passed_to_gdctl(self):
        command = lib.build_gdctl_command(self.profile, "top", "normal", self.config(mode="2880x1800@119.998"))
        self.assertIn("--mode", command)
        self.assertIn("2880x1800@119.998", command)

    def test_attached_detached_and_rotation_policy(self):
        self.assertEqual(helper.layout_for_policy(True), "top")
        self.assertEqual(helper.layout_for_policy(False), "both")
        for attached in (True, False):
            self.assertEqual(helper.layout_for_policy(attached), "top" if attached else "both")
        self.assertEqual(lib.transform_for("left-up"), "90")
        self.assertEqual(lib.transform_for("right-up"), "270")
        attached_left = lib.build_gdctl_command(self.profile, helper.layout_for_policy(True), "left-up", self.config())
        attached_right = lib.build_gdctl_command(self.profile, helper.layout_for_policy(True), "right-up", self.config())
        detached_left = lib.build_gdctl_command(self.profile, helper.layout_for_policy(False), "left-up", self.config())
        detached_right = lib.build_gdctl_command(self.profile, helper.layout_for_policy(False), "right-up", self.config())
        self.assertIn("90", attached_left)
        self.assertIn("270", attached_right)
        self.assertIn("--right-of", detached_left)
        self.assertIn("--right-of", detached_right)

    def test_usb_transition_and_keyboard_fixture(self):
        self.assertFalse(lib.dock_state_changed(True, True))
        self.assertTrue(lib.dock_state_changed(True, False))
        with tempfile.TemporaryDirectory() as directory:
            usb = Path(directory) / "1-1"
            usb.mkdir()
            (usb / "idVendor").write_text("0b05\n")
            (usb / "idProduct").write_text("1b2c\n")
            self.assertTrue(lib.keyboard_attached(self.profile, Path(directory)))

    def test_toggle_and_external_monitor_protection(self):
        self.assertEqual(lib.toggle_target({"eDP-1", "eDP-2"}, "eDP-1", "eDP-2"), "top")
        self.assertEqual(lib.toggle_target({"eDP-1"}, "eDP-1", "eDP-2"), "both")
        self.assertEqual(lib.toggle_target({"eDP-2"}, "eDP-1", "eDP-2"), "both")
        self.assertTrue(lib.has_external_monitor({"eDP-1", "eDP-2", "HDMI-A-1"}, {"eDP-1", "eDP-2"}))
        self.assertFalse(lib.has_external_monitor({"eDP-1", "eDP-2"}, {"eDP-1", "eDP-2"}))

    def test_external_monitor_suppresses_automatic_layout_but_force_allows_it(self):
        config = self.config()
        with mock.patch.object(helper, "read_config", return_value=config), \
             mock.patch.object(helper, "connected_connectors", return_value={"eDP-1", "eDP-2", "HDMI-A-1"}), \
             mock.patch.object(helper, "panels_available", return_value=True), \
             mock.patch.object(helper.subprocess, "run") as run:
            self.assertFalse(helper.apply_layout(self.profile, "both", force=False, drm_root=Path("/fixture")))
            run.assert_not_called()
            run.return_value = mock.Mock()
            self.assertTrue(helper.apply_layout(self.profile, "both", force=True, drm_root=Path("/fixture")))
            self.assertEqual(run.call_args.args[0][:4], ["gdctl", "set", "--layout-mode", "logical"])

    def test_auto_scale_falls_back_to_two_when_fractional_scale_is_rejected(self):
        config = self.config()
        failure = helper.subprocess.CalledProcessError(1, ["gdctl"])
        with mock.patch.object(helper, "read_config", return_value=config), \
             mock.patch.object(helper, "connected_connectors", return_value={"eDP-1", "eDP-2"}), \
             mock.patch.object(helper, "panels_available", return_value=True), \
             mock.patch.object(helper.subprocess, "run", side_effect=[failure, failure, failure, failure, mock.Mock()]) as run, \
             mock.patch.object(helper.time, "sleep"):
            self.assertTrue(helper.apply_layout(self.profile, "both", drm_root=Path("/fixture")))
            self.assertIn("2", run.call_args.args[0])

    def test_missing_panel_and_backlight_are_safe(self):
        self.assertFalse(lib.panels_available({"eDP-1"}, "eDP-1", "eDP-2"))
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(lib.find_backlight(("intel_backlight",), Path(directory)))

    def test_missing_sensor_is_optional(self):
        with mock.patch.object(helper.subprocess, "Popen", side_effect=FileNotFoundError):
            self.assertEqual(helper.watch_rotation(self.profile), 0)

    def test_brightness_and_charge_validation(self):
        self.assertEqual(lib.brightness_value(50, 100, 200), 100)
        self.assertEqual(lib.brightness_value(1, 100, 200), 2)
        self.assertEqual(lib.brightness_value(200, 100, 200), 200)
        self.assertEqual(lib.validate_charge_limit("80"), 80)
        with self.assertRaises(ValueError):
            lib.validate_charge_limit(0)
        with self.assertRaises(ValueError):
            lib.validate_charge_limit(101)

    def test_gdctl_show_toggle_parser(self):
        output = """Monitors:\n└──Monitor eDP-1\n└──Monitor eDP-2\nLogical monitors:\n└──Logical monitor #1\n   └──Monitors: (1)\n       └──eDP-1\n└──Logical monitor #2\n   └──Monitors: (1)\n       └──eDP-2\n"""
        self.assertEqual(lib.active_internal_connectors(output, ("eDP-1", "eDP-2")), {"eDP-1", "eDP-2"})


if __name__ == "__main__":
    unittest.main()

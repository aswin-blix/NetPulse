"""Preference validation, persistence recovery, and multi-monitor placement."""

import json
import math
import os
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from settings import Settings, default_path, load_settings, reset_appearance, save_settings
from windows import clamp_position


class SettingsValidationTests(unittest.TestCase):
    def test_valid_preferences_round_trip(self):
        expected = Settings(
            theme="light",
            accent="violet",
            size="mini",
            units="bytes",
            interval=2.0,
            opacity=0.8,
            corner_radius=7,
            topmost=False,
            graphs=False,
            adapter="adapter-guid",
            x=-500,
            y=40,
        )
        self.assertEqual(Settings.from_dict(asdict(expected)), expected)

    def test_non_dictionary_and_empty_inputs_use_defaults(self):
        for data in (None, [], "dark", 42, {}):
            with self.subTest(data=data):
                self.assertEqual(Settings.from_dict(data), Settings())

    def test_unknown_keys_are_ignored(self):
        self.assertEqual(Settings.from_dict({"future_setting": "x", "theme": "dark"}).theme, "dark")

    def test_invalid_enum_values_use_defaults(self):
        result = Settings.from_dict({"theme": "sepia", "accent": [], "size": 2, "units": "binary"})
        self.assertEqual(result, Settings())

    def test_numeric_ranges_are_clamped(self):
        low = Settings.from_dict({"interval": -10, "opacity": -1})
        high = Settings.from_dict({"interval": 100, "opacity": 100})
        self.assertEqual((low.interval, low.opacity), (0.5, 0.65))
        self.assertEqual((high.interval, high.opacity), (3.0, 1.0))

    def test_non_finite_and_non_numeric_preferences_are_ignored(self):
        for value in (math.inf, -math.inf, math.nan, "1", True, None, []):
            with self.subTest(value=value):
                result = Settings.from_dict({"interval": value, "opacity": value})
                self.assertEqual((result.interval, result.opacity), (1.0, 1.0))

    def test_extreme_json_integer_does_not_prevent_loading(self):
        # Valid JSON integers need not fit in a float; math.isfinite can overflow.
        for value in (10**400, -(10**400)):
            with self.subTest(sign=value > 0):
                result = Settings.from_dict({"interval": value, "opacity": value})
                self.assertTrue(0.5 <= result.interval <= 3.0)
                self.assertTrue(0.65 <= result.opacity <= 1.0)

    def test_boolean_fields_require_real_booleans(self):
        for value in (0, 1, "false", None, []):
            result = Settings.from_dict({"topmost": value, "graphs": value})
            self.assertTrue(result.topmost and result.graphs)
        result = Settings.from_dict({"topmost": False, "graphs": False})
        self.assertFalse(result.topmost or result.graphs)

    def test_corner_radius_defaults_clamps_and_preserves_custom_values(self):
        self.assertEqual(Settings.from_dict({}).corner_radius, 12)
        for value, expected in ((0, 0), (7, 7), (24, 24), (-1, 0), (10**400, 24)):
            with self.subTest(value=value):
                self.assertEqual(
                    Settings.from_dict({"corner_radius": value}).corner_radius, expected
                )

    def test_invalid_corner_radius_uses_default(self):
        for value in (True, False, "7", None, [], math.nan, math.inf, 7.5):
            with self.subTest(value=value):
                self.assertEqual(Settings.from_dict({"corner_radius": value}).corner_radius, 12)

    def test_coordinates_are_kept_together_and_accept_negative_monitors(self):
        valid = Settings.from_dict({"x": -1920, "y": -1080})
        self.assertEqual((valid.x, valid.y), (-1920, -1080))
        for data in (
            {"x": 100},
            {"x": 100, "y": None},
            {"x": True, "y": 20},
            {"x": 10.5, "y": 20},
            {"x": "10", "y": "20"},
        ):
            result = Settings.from_dict(data)
            self.assertEqual((result.x, result.y), (None, None))

    def test_adapter_selection_validation(self):
        for value in (None, "", 42, "x" * 300):
            self.assertEqual(Settings.from_dict({"adapter": value}).adapter, "auto")
        self.assertEqual(Settings.from_dict({"adapter": "x" * 299}).adapter, "x" * 299)

    def test_reset_preserves_adapter_and_placement(self):
        settings = Settings(
            theme="dark",
            accent="peach",
            units="bytes",
            interval=2,
            opacity=0.65,
            corner_radius=0,
            topmost=False,
            graphs=False,
            adapter="vpn-guid",
            x=-750,
            y=12,
        )
        reset_appearance(settings)
        self.assertEqual(settings, Settings(adapter="vpn-guid", x=-750, y=12))


class SettingsPersistenceTests(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        with patch.object(Path, "read_text", side_effect=FileNotFoundError):
            self.assertEqual(load_settings(Path("missing.json")), Settings())

    def test_corrupt_or_unreadable_file_returns_defaults(self):
        for value in ("{invalid", "null", "[]", '"text"', '{"interval": NaN}'):
            with patch.object(Path, "read_text", return_value=value):
                self.assertEqual(load_settings(Path("settings.json")), Settings())
        for error in (PermissionError(), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")):
            with patch.object(Path, "read_text", side_effect=error):
                self.assertEqual(load_settings(Path("settings.json")), Settings())

    def test_corrupt_huge_integer_file_does_not_crash(self):
        contents = '{"interval": ' + "9" * 401 + ', "theme": "light"}'
        with patch.object(Path, "read_text", return_value=contents):
            result = load_settings(Path("settings.json"))
        self.assertTrue(0.5 <= result.interval <= 3.0)

    def test_default_location_uses_local_app_data(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": "C:/Users/Example/AppData/Local"}):
            self.assertEqual(
                default_path(), Path("C:/Users/Example/AppData/Local/NetPulse/settings.json")
            )

    def test_real_atomic_round_trip_and_replacement_failure(self):
        # Extended Windows paths also work in the desktop runtime's file sandbox.
        base = tempfile.gettempdir()
        if os.name == "nt" and not base.startswith("\\\\?\\"):
            base = "\\\\?\\" + str(Path(base).resolve())
        with tempfile.TemporaryDirectory(prefix="netpulse-test-", dir=base) as directory:
            path = Path(directory) / "nested" / "settings.json"
            original = Settings(theme="dark", corner_radius=7, x=-20, y=30)
            save_settings(original, path)
            self.assertEqual(load_settings(path), original)
            self.assertFalse(path.with_suffix(".tmp").exists())
            with (
                patch.object(Path, "replace", side_effect=PermissionError("blocked")),
                self.assertRaises(PermissionError),
            ):
                save_settings(Settings(theme="light"), path)
            # A failed final rename must leave the previous good file untouched.
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["theme"], "dark")


class ClampPositionTests(unittest.TestCase):
    def setUp(self):
        self.primary = (0, 0, 1920, 1040)
        self.left = (-1280, 0, 0, 984)

    def test_visible_position_is_unchanged(self):
        self.assertEqual(clamp_position(100, 200, 260, 120, [self.primary]), (100, 200))

    def test_right_and_bottom_edges_respect_taskbar_work_area(self):
        self.assertEqual(clamp_position(1900, 1000, 260, 120, [self.primary]), (1660, 920))

    def test_negative_monitor_position_is_preserved(self):
        self.assertEqual(
            clamp_position(-1000, 200, 260, 120, [self.primary, self.left]), (-1000, 200)
        )

    def test_removed_monitor_position_moves_to_nearest_visible_edge(self):
        self.assertEqual(clamp_position(-1000, 200, 260, 120, [self.primary]), (0, 200))

    def test_window_is_wholly_on_one_monitor(self):
        self.assertEqual(clamp_position(-100, 200, 260, 120, [self.primary, self.left]), (0, 200))

    def test_monitor_above_primary(self):
        above = (0, -1080, 1920, 0)
        self.assertEqual(clamp_position(400, -1000, 260, 120, [self.primary, above]), (400, -1000))

    def test_tiny_work_area_retains_accessible_top_left(self):
        self.assertEqual(clamp_position(100, 100, 260, 120, [(0, 0, 200, 100)]), (0, 0))

    def test_empty_work_areas_preserve_fallback_position(self):
        self.assertEqual(clamp_position(-20, 200, 260, 120, []), (-20, 200))

    def test_extreme_stored_coordinates_clamp_without_overflow(self):
        self.assertEqual(clamp_position(10**400, -(10**400), 260, 120, [self.primary]), (1660, 0))


if __name__ == "__main__":
    unittest.main()

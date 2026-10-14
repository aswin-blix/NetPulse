"""Windows UI integration tests. Run in a desktop session with Tk installed."""

import ctypes as c
import sys
import tempfile
import tkinter as tk
import unittest
from ctypes import wintypes as w
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch

from app import NetPulse
from network import Adapter, Reading
from settings import load_settings
from windows import enable_dpi_awareness, native_handle


class FakeReader:
    def __init__(self):
        self.fail = False

    def read(self):
        if self.fail:
            raise OSError("Counter access failed")
        return [Adapter("wifi", "Wi-Fi", 1000, 500, True, True, False, False)]


@unittest.skipUnless(sys.platform == "win32", "Windows desktop integration")
class WidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        enable_dpi_awareness()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="netpulse-ui-")
        self.config = Path(self.temp.name) / "settings.json"
        self.reader = FakeReader()
        self.root = tk.Tk()
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)
        self.app = NetPulse(self.root, self.config, self.reader)
        self.root.update()

    def tearDown(self):
        self.root.update()
        self.app.close()
        self.temp.cleanup()
        self.assertEqual(self.errors, [])

    def test_all_themes_sizes_and_units_fit(self):
        for theme in ("dark", "light", "system"):
            self.app.change("theme", theme)
            for size in ("mini", "compact", "comfortable"):
                self.app.change("size", size)
                for units in ("bits", "bytes"):
                    self.app.change("units", units)
                    for rate in (0, 124875, 12498750, 2e14):
                        self.app.reading = Reading(rate, rate, "live", ("Wi-Fi",))
                        self.app.draw()
                        cv = self.app.canvas
                        text_items = [i for i in cv.find_all() if cv.type(i) == "text"]
                        for item in text_items:
                            box = cv.bbox(item)
                            self.assertGreaterEqual(box[0], 0)
                            self.assertLessEqual(box[2], self.app.width)
                            self.assertLessEqual(box[3], self.app.height)
                        # Every number/unit pair on the same row must have a gap.
                        rate_y = self.app.px(18 if size == "mini" else 66)
                        unit_y = self.app.px(20 if size == "mini" else 70)
                        numbers = [
                            i
                            for i in text_items
                            if cv.coords(i)[1] == rate_y
                            and cv.itemcget(i, "text") not in ("↓", "↑")
                        ]
                        units_items = [i for i in text_items if cv.coords(i)[1] == unit_y]
                        self.assertEqual(len(numbers), 2)
                        self.assertEqual(len(units_items), 2)
                        for number, unit in zip(numbers, units_items, strict=True):
                            self.assertLess(cv.bbox(number)[2], cv.bbox(unit)[0])

    def test_settings_selection_binding_changes_theme(self):
        self.app.open_settings()
        body = self.app.dialog.winfo_children()[0]
        combo = next(child for child in body.winfo_children() if isinstance(child, ttk.Combobox))
        combo.current(2)
        combo.event_generate("<<ComboboxSelected>>")
        self.root.update()
        self.assertEqual(self.app.settings.theme, "light")
        self.assertEqual(self.app.theme, "light")
        self.assertEqual(load_settings(self.config).theme, "light")

    def test_corner_radius_slider_changes_live_and_saves(self):
        self.app.open_settings()
        body = self.app.dialog.winfo_children()[0]
        slider = next(
            child
            for frame in body.winfo_children()
            for child in frame.winfo_children()
            if isinstance(child, tk.Scale)
        )
        slider.set(7)
        self.root.update()
        self.assertEqual(self.app.settings.corner_radius, 7)
        self.assertEqual(load_settings(self.config).corner_radius, 7)
        self.app.change("theme", "light")
        self.assertEqual(self.app.settings.corner_radius, 7)
        self.app.reset_style()
        self.assertEqual(self.app.settings.corner_radius, 12)

    def test_corner_radius_updates_native_region_in_every_size(self):
        user, gdi = c.windll.user32, c.windll.gdi32
        user.GetWindowRgn.argtypes = [w.HWND, w.HRGN]
        gdi.CreateRectRgn.argtypes = [c.c_int] * 4
        gdi.CreateRectRgn.restype = w.HRGN
        gdi.PtInRegion.argtypes = [w.HRGN, c.c_int, c.c_int]
        gdi.DeleteObject.argtypes = [w.HGDIOBJ]
        region = gdi.CreateRectRgn(0, 0, 0, 0)
        try:
            for size in ("mini", "compact", "comfortable"):
                self.app.change("size", size)
                for radius in (7, 24, 0, 12):
                    self.app.change("corner_radius", radius)
                    result = user.GetWindowRgn(native_handle(self.root), region)
                    if radius == 0:
                        self.assertEqual(
                            result, 0
                        )  # A null window region restores the full rectangle.
                    else:
                        self.assertNotEqual(result, 0)
                        self.assertFalse(gdi.PtInRegion(region, 0, 0))
                        self.assertTrue(
                            gdi.PtInRegion(region, self.app.width // 2, self.app.height // 2)
                        )
        finally:
            gdi.DeleteObject(region)

    def test_settings_opens_once_and_dismisses(self):
        self.app.open_settings()
        original = self.app.dialog
        self.app.open_settings()
        self.assertIs(self.app.dialog, original)
        self.app.dismiss()
        self.assertIsNone(self.app.dialog)

    def test_settings_icon_mouse_binding(self):
        x, y = self.app.px(self.app.logical_width - 38), self.app.px(15)
        self.app.canvas.event_generate("<ButtonPress-1>", x=x, y=y)
        self.app.canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
        self.root.update()
        self.assertIsNotNone(self.app.dialog)
        self.assertEqual(self.app.dialog.title(), "Customize NetPulse")

    def test_mini_has_only_readings_and_no_header_hitboxes(self):
        self.app.change("size", "mini")
        self.app.reading = Reading(1550000, 262500, "live", ("Wi-Fi",))
        self.app.draw()
        labels = [
            self.app.canvas.itemcget(i, "text")
            for i in self.app.canvas.find_all()
            if self.app.canvas.type(i) == "text"
        ]
        self.assertEqual(labels, ["↓", "12.4", "Mbps", "↑", "2.10", "Mbps"])
        self.assertEqual(self.app.logical_height, 38)
        self.assertEqual(self.app.hitboxes, {})

    def test_mini_right_click_opens_customization(self):
        self.app.change("size", "mini")
        self.root.update()
        with patch.object(tk.Menu, "tk_popup"):
            self.app.canvas.event_generate("<Button-3>", x=20, y=18)
        self.assertIsNotNone(self.app.menu)
        self.app.menu.invoke(0)
        self.assertIsNotNone(self.app.dialog)
        self.app.change("size", "compact")
        self.assertIn("settings", self.app.hitboxes)

    def test_context_menu_replaces_previous_menu(self):
        event = SimpleNamespace(x_root=100, y_root=100)
        with patch.object(tk.Menu, "tk_popup"):
            self.app.context_menu(event)
            old_menu = self.app.menu
            self.app.context_menu(event)
        self.assertFalse(old_menu.winfo_exists())
        menus = [child for child in self.root.winfo_children() if isinstance(child, tk.Menu)]
        self.assertEqual(len(menus), 1)

    def test_drag_binding_moves_and_saves(self):
        for size in ("compact", "mini"):
            self.app.change("size", size)
            self.root.update()
            before = self.app.position
            canvas = self.app.canvas
            canvas.event_generate("<ButtonPress-1>", x=30, y=18, rootx=100, rooty=100)
            canvas.event_generate("<B1-Motion>", x=20, y=8, rootx=90, rooty=90)
            canvas.event_generate("<ButtonRelease-1>", x=20, y=8, rootx=90, rooty=90)
            self.assertEqual(self.app.position, (before[0] - 10, before[1] - 10))
            self.assertEqual(load_settings(self.config).x, before[0] - 10)

    def test_opacity_and_topmost_change(self):
        self.app.change("opacity", 0.8)
        self.app.change("topmost", False)
        self.root.update()
        self.assertAlmostEqual(self.root.attributes("-alpha"), 0.8, places=2)
        self.assertFalse(self.root.attributes("-topmost"))

    def test_adapter_change_warms_and_clears_graph(self):
        self.app.history.append((10, 5))
        self.app.change("adapter", "wifi")
        self.assertEqual(self.app.reading.status, "warming")
        self.assertFalse(self.app.history)

    def test_read_failure_recovers_without_spike(self):
        self.reader.fail = True
        self.root.after_cancel(self.app.timer)
        self.app._poll()
        self.assertEqual(self.app.reading.status, "unavailable")
        self.reader.fail = False
        self.root.after_cancel(self.app.timer)
        self.app._poll()
        self.assertEqual(self.app.reading.status, "warming")

    def test_missing_adapter_is_unavailable(self):
        self.app.change("adapter", "missing")
        self.assertEqual(self.app.reading.status, "unavailable")
        self.app.open_settings()
        self.root.update()

    def test_reset_preserves_adapter_and_position(self):
        before = self.app.position
        self.app.change("adapter", "wifi")
        self.app.change("theme", "light")
        self.app.change("units", "bytes")
        self.app.reset_style()
        self.assertEqual(self.app.settings.units, "bits")
        self.assertEqual(self.app.settings.theme, "system")
        self.assertEqual(self.app.settings.adapter, "wifi")
        self.assertEqual(self.app.position, before)


if __name__ == "__main__":
    unittest.main()

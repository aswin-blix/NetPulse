"""NetPulse: a small, local-only Windows network traffic widget."""

from __future__ import annotations

import argparse
import ctypes
import sys
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import messagebox, ttk

from network import RateSampler, Reading, WindowsNetworkReader, format_rate
from settings import default_path, load_settings, reset_appearance, save_settings
from tk_runtime_hook import configure_tcl_paths
from windows import (
    clamp_position,
    enable_dpi_awareness,
    move_window,
    single_instance,
    style_window,
    system_theme,
    work_areas,
)

configure_tcl_paths()

PALETTES = {
    "dark": {
        "bg": "#111827",
        "card": "#192334",
        "edge": "#2A374B",
        "text": "#F2F6FC",
        "muted": "#9AAAC0",
        "faint": "#42536C",
        "up": "#91B9FF",
        "hover": "#26374F",
    },
    "light": {
        "bg": "#F6F8FC",
        "card": "#E9EFF7",
        "edge": "#CBD5E4",
        "text": "#15233B",
        "muted": "#53647B",
        "faint": "#B1BFD1",
        "up": "#3466CE",
        "hover": "#DCE6F4",
    },
}
ACCENTS = {
    "mint": ("#64E1BC", "#087A5A"),
    "blue": ("#71CCFF", "#006B9C"),
    "violet": ("#C1A4FF", "#7344B3"),
    "peach": ("#FFB491", "#A5481F"),
}


class NetPulse:
    def __init__(self, root: tk.Tk, config: Path | None = None, reader=None):
        self.root = root
        self.config = config or default_path()
        self.settings = load_settings(self.config)
        self.reader = reader or WindowsNetworkReader()
        self.sampler = RateSampler()
        self.adapters = []
        self.reading = Reading(0.0, 0.0, "warming", ())
        self.history = deque(maxlen=48)
        self.dialog = None
        self.menu = None
        self.timer = None
        self.theme_timer = None
        self.drag = None
        self.active_action = None
        self.hover = None
        self.save_error = False
        self.last_error = ""
        self.help_tip = None
        self.tip_timer = None
        root.withdraw()
        root.title("NetPulse")
        icon = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "NetPulse.ico"
        if icon.exists():
            root.iconbitmap(default=str(icon))
        root.overrideredirect(True)
        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", self.context_menu)
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<Leave>", self._leave)
        root.bind("<Control-comma>", lambda _e: self.open_settings())
        root.bind("<Control-q>", lambda _e: self.close())
        root.bind("<Escape>", lambda _e: self.dismiss())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._apply_appearance()
        root.update_idletasks()
        areas = self._areas()
        if self.settings.x is None:
            area = next((a for a in areas if a[0] <= 0 < a[2] and a[1] <= 0 < a[3]), areas[0])
            x, y = area[2] - self.width - 24, area[3] - self.height - 24
        else:
            x, y = self.settings.x, self.settings.y
        self.position = clamp_position(x, y, self.width, self.height, areas)
        root.deiconify()
        root.update_idletasks()
        move_window(root, *self.position)
        style_window(root, self.width, self.height, self.px(self.settings.corner_radius))
        self._poll()
        self._watch_theme()

    def _areas(self):
        return work_areas() or [
            (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        ]

    def px(self, value):
        return round(value * self.scale)

    def font(self, size, weight="normal"):
        return ("Segoe UI", -self.px(size), weight)

    def _apply_appearance(self):
        s = self.settings
        self.theme = system_theme() if s.theme == "system" else s.theme
        self.colors = dict(PALETTES[self.theme])
        self.colors["accent"] = ACCENTS[s.accent][self.theme == "light"]
        self.scale = max(1.0, self.root.winfo_fpixels("1i") / 96)
        if s.size == "comfortable":
            self.scale *= 1.2
        self.logical_width = 226 if s.size == "mini" else 260
        self.logical_height = 38 if s.size == "mini" else (120 if s.graphs else 102)
        self.width, self.height = self.px(self.logical_width), self.px(self.logical_height)
        self.root.geometry(f"{self.width}x{self.height}")
        self.root.configure(bg=self.colors["bg"])
        self.canvas.configure(bg=self.colors["bg"], width=self.width, height=self.height)
        self.root.attributes("-topmost", s.topmost)
        self.root.attributes("-alpha", s.opacity)
        self.root.update_idletasks()
        if hasattr(self, "position"):
            self.position = clamp_position(*self.position, self.width, self.height, self._areas())
            move_window(self.root, *self.position)
        style_window(self.root, self.width, self.height, self.px(s.corner_radius))
        self.draw()

    def _watch_theme(self):
        if self.settings.theme == "system" and system_theme() != self.theme:
            self._apply_appearance()
            if self.dialog is not None:
                self._build_settings()
        # Recover from a removed monitor, even when the user has not dragged.
        pos = clamp_position(*self.position, self.width, self.height, self._areas())
        if pos != self.position and not self.drag:
            self.position = pos
            move_window(self.root, *pos)
        self.theme_timer = self.root.after(3000, self._watch_theme)

    def _poll(self):
        started = time.perf_counter()
        try:
            self.adapters = self.reader.read()
            self.reading = self.sampler.update(
                self.adapters, time.perf_counter(), self.settings.adapter
            )
            self.last_error = ""
        except OSError as error:
            self.last_error = str(error)
            self.reading = Reading(0.0, 0.0, "unavailable", ())
            self.sampler = RateSampler()
        if self.reading.status == "live":
            self.history.append((self.reading.download, self.reading.upload))
        else:
            self.history.clear()
        self.draw()
        delay = max(50, round((self.settings.interval - (time.perf_counter() - started)) * 1000))
        self.timer = self.root.after(delay, self._poll)

    def _text(self, x, y, text, size, color, weight="normal", anchor="w"):
        return self.canvas.create_text(
            self.px(x),
            self.px(y),
            text=text,
            fill=color,
            font=self.font(size, weight),
            anchor=anchor,
        )

    def _line(self, *coords, **kwargs):
        return self.canvas.create_line(*(self.px(v) for v in coords), **kwargs)

    def _status(self):
        status = self.reading.status
        if self.save_error:
            return "Preferences not saved"
        if self.last_error:
            return "Reading unavailable"
        if status == "warming":
            return "Measuring…"
        if status == "offline":
            return "Adapter disconnected"
        if status == "unavailable":
            return "Choose an adapter"
        names = self.reading.names
        name = names[0] if len(names) == 1 else f"{len(names)} adapters"
        return name if len(name) < 20 else name[:18] + "…"

    def draw(self):
        cv, c, mini = self.canvas, self.colors, self.settings.size == "mini"
        cv.delete("all")
        width = self.logical_width
        # A quiet accent rule and generous internal spacing keep the tiny card legible.
        self._line(16, 1, width - 16, 1, fill=c["edge"], width=1)
        self.hitboxes = {}
        if not mini:
            dot = c["accent"] if self.reading.status == "live" else c["muted"]
            cv.create_oval(self.px(13), self.px(12), self.px(18), self.px(17), fill=dot, outline="")
            self._text(25, 15, "NETPULSE", 9, c["muted"], "bold")
            self._text(93, 15, self._status(), 9, c["muted"])
            self.hitboxes = {
                "settings": (width - 50, 3, width - 26, 28),
                "close": (width - 26, 3, width - 3, 28),
            }
            for action, (left, top, right, bottom) in self.hitboxes.items():
                if self.hover == action:
                    cv.create_oval(
                        self.px(left + 1),
                        self.px(top + 1),
                        self.px(right - 1),
                        self.px(bottom - 1),
                        fill=c["hover"],
                        outline="",
                    )
            # Draw the control icons as lines so they remain sharp at every Windows scale.
            gx, gy = width - 38, 15
            for dy, knob in ((-4, -3), (0, 3), (4, -1)):
                self._line(gx - 6, gy + dy, gx + 6, gy + dy, fill=c["muted"], width=self.px(1))
                self._line(
                    gx + knob, gy + dy - 2, gx + knob, gy + dy + 2, fill=c["text"], width=self.px(2)
                )
            self._line(width - 18, 11, width - 11, 18, fill=c["muted"], width=self.px(1))
            self._line(width - 18, 18, width - 11, 11, fill=c["muted"], width=self.px(1))
        middle = width / 2
        self._line(
            middle,
            8 if mini else 36,
            middle,
            self.logical_height - (8 if mini else 15),
            fill=c["edge"],
            width=1,
        )
        for index, (label, arrow, rate, color) in enumerate(
            (
                ("DOWNLOAD", "↓", self.reading.download, c["accent"]),
                ("UPLOAD", "↑", self.reading.upload, c["up"]),
            )
        ):
            left = 14 + index * middle
            value, unit = format_rate(rate, self.settings.units)
            if self.reading.status != "live":
                value, unit = "—", ""
            if mini:
                self._text(left, 18, arrow, 17, color, "bold")
                item = self._text(left + 17, 18, value, 17, c["text"], "bold")
                box = cv.bbox(item)
                self._text(box[2] / self.scale + 3, 20, unit, 8, c["muted"])
            else:
                self._text(left, 40, arrow + "  " + label, 9, color, "bold")
                item = self._text(
                    left - 1, 66, value, 26 if len(value) < 6 else 22, c["text"], "bold"
                )
                box = cv.bbox(item)
                unit_x = min(left + middle - 36, box[2] / self.scale + 5)
                self._text(unit_x, 70, unit, 10, c["muted"])
                if self.settings.graphs:
                    self._graph(left, 103, middle - 29, index, color)
        if not mini:
            note = "LIVE TRAFFIC" if self.reading.status == "live" else self._status().upper()
            self._text(14, 87, note, 8, c["muted"])

    def _graph(self, x, y, width, index, color):
        self._line(x, y + 9, x + width, y + 9, fill=self.colors["edge"], width=1)
        values = [sample[index] for sample in self.history]
        if len(values) < 2:
            return
        peak = max(1024, max(values))
        points = []
        for offset, value in enumerate(values):
            points.extend((x + width * (48 - len(values) + offset) / 47, y + 9 - 16 * value / peak))
        self._line(*points, fill=color, width=self.px(1.5), capstyle="round", joinstyle="round")

    def _action(self, event):
        x, y = event.x / self.scale, event.y / self.scale
        return next(
            (
                key
                for key, (left, top, right, bottom) in self.hitboxes.items()
                if left <= x <= right and top <= y <= bottom
            ),
            None,
        )

    def _press(self, event):
        self._hide_tip()
        self.active_action = self._action(event)
        if self.active_action is None:
            self.drag = (event.x_root, event.y_root, *self.position)

    def _drag(self, event):
        if self.drag:
            start_x, start_y, x, y = self.drag
            self.position = (x + event.x_root - start_x, y + event.y_root - start_y)
            move_window(self.root, *self.position)

    def _release(self, event):
        if self.drag:
            self.drag = None
            self.position = clamp_position(*self.position, self.width, self.height, self._areas())
            move_window(self.root, *self.position)
            self.persist()
        elif self.active_action == self._action(event):
            if self.active_action == "settings":
                self.open_settings()
            elif self.active_action == "close":
                self.close()
        self.active_action = None

    def _hover(self, event):
        action = self._action(event)
        if action != self.hover:
            self.hover = action
            self.canvas.configure(cursor="hand2" if action else "fleur")
            self.draw()
            self._hide_tip()
        if self.tip_timer is None and self.help_tip is None:
            self.tip_timer = self.root.after(850, self._show_tip)

    def _leave(self, _event):
        self.hover = None
        self._hide_tip()
        self.draw()

    def _show_tip(self):
        self.tip_timer = None
        if self.drag:
            return
        text = {"settings": "Customize NetPulse · Ctrl+,", "close": "Close NetPulse · Ctrl+Q"}.get(
            self.hover
        )
        if text is None:
            text = self._status() + "\nDrag to move · Right-click for options"
        tip = self.help_tip = tk.Toplevel(self.root)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        tk.Label(
            tip,
            text=text,
            bg=self.colors["card"],
            fg=self.colors["text"],
            padx=12,
            pady=8,
            font=("Segoe UI", 9),
            justify="left",
        ).pack()
        tip.update_idletasks()
        x, y = clamp_position(
            self.position[0],
            self.position[1] - tip.winfo_reqheight() - 6,
            tip.winfo_reqwidth(),
            tip.winfo_reqheight(),
            self._areas(),
        )
        move_window(tip, x, y)

    def _hide_tip(self):
        if self.tip_timer is not None:
            self.root.after_cancel(self.tip_timer)
            self.tip_timer = None
        if self.help_tip is not None:
            self.help_tip.destroy()
            self.help_tip = None

    def persist(self):
        self.settings.x, self.settings.y = self.position
        try:
            save_settings(self.settings, self.config)
            self.save_error = False
        except OSError:
            self.save_error = True

    def change(self, key, value):
        setattr(self.settings, key, value)
        if key == "adapter":
            self.sampler = RateSampler()
            self.history.clear()
            self.reading = Reading(0.0, 0.0, "warming", ())
        self._hide_tip()
        self._apply_appearance()
        self.persist()
        if self.dialog is not None and key in ("theme", "accent"):
            self._build_settings()
        if key in ("interval", "adapter"):
            self.root.after_cancel(self.timer)
            self._poll()

    def context_menu(self, event):
        self._hide_tip()
        if self.menu is not None:
            self.menu.destroy()
        c = self.colors
        menu = self.menu = tk.Menu(
            self.root,
            tearoff=False,
            bg=c["card"],
            fg=c["text"],
            activebackground=c["hover"],
            activeforeground=c["accent"],
            relief="flat",
            borderwidth=1,
            font=("Segoe UI", 10),
        )
        menu.add_command(label="Customize…     Ctrl+,", command=self.open_settings)
        menu.add_separator()
        for key, label in (
            ("dark", "Dark theme"),
            ("light", "Light theme"),
            ("system", "Follow Windows"),
        ):
            mark = "✓  " if self.settings.theme == key else "    "
            menu.add_command(label=mark + label, command=lambda v=key: self.change("theme", v))
        menu.add_separator()
        menu.add_command(
            label=("✓  " if self.settings.topmost else "    ") + "Always on top",
            command=lambda: self.change("topmost", not self.settings.topmost),
        )
        menu.add_command(label="Help & measurement details", command=self.show_help)
        menu.add_separator()
        menu.add_command(label="Exit NetPulse", command=self.close)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def dismiss(self):
        self._hide_tip()
        if self.dialog is not None:
            self.dialog.destroy()
            self.dialog = None

    def open_settings(self):
        self._hide_tip()
        if self.dialog is not None:
            self.dialog.lift()
            return
        dialog = self.dialog = tk.Toplevel(self.root)
        dialog.title("Customize NetPulse")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.protocol("WM_DELETE_WINDOW", self.dismiss)
        dialog.bind("<Escape>", lambda _e: self.dismiss())
        self._build_settings()
        dialog.update_idletasks()
        center_x = self.position[0] + self.width // 2
        center_y = self.position[1] + self.height // 2
        areas = self._areas()
        area = next(
            (a for a in areas if a[0] <= center_x < a[2] and a[1] <= center_y < a[3]),
            min(
                areas,
                key=lambda a: (
                    (max(a[0] - center_x, 0, center_x - a[2])) ** 2
                    + (max(a[1] - center_y, 0, center_y - a[3])) ** 2
                ),
            ),
        )
        x = area[0] + (area[2] - area[0] - dialog.winfo_reqwidth()) // 2
        y = area[1] + (area[3] - area[1] - dialog.winfo_reqheight()) // 2
        move_window(dialog, x, y)
        dialog.lift()

    def _build_settings(self):
        dialog, c = self.dialog, self.colors
        for child in dialog.winfo_children():
            child.destroy()
        dialog.configure(bg=c["bg"])
        style = ttk.Style(dialog)
        style.theme_use("clam")
        style.configure(
            "NP.TCombobox",
            fieldbackground=c["card"],
            background=c["card"],
            foreground=c["text"],
            arrowcolor=c["muted"],
            bordercolor=c["edge"],
            padding=6,
        )
        style.map(
            "NP.TCombobox",
            fieldbackground=[("readonly", c["card"])],
            foreground=[("readonly", c["text"])],
            selectbackground=[("readonly", c["card"])],
            selectforeground=[("readonly", c["text"])],
        )
        dialog.option_add("*TCombobox*Listbox.background", c["card"])
        dialog.option_add("*TCombobox*Listbox.foreground", c["text"])
        dialog.option_add("*TCombobox*Listbox.selectBackground", c["hover"])
        body = tk.Frame(dialog, bg=c["bg"], padx=24, pady=20)
        body.pack(fill="both", expand=True)
        tk.Label(
            body, text="Make it yours.", font=("Segoe UI", 20, "bold"), bg=c["bg"], fg=c["text"]
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(
            body,
            text="A little window into your connection.",
            font=("Segoe UI", 10),
            bg=c["bg"],
            fg=c["muted"],
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 17))
        row = 2

        def select(label, key, options):
            nonlocal row
            tk.Label(body, text=label, bg=c["bg"], fg=c["text"], font=("Segoe UI", 10)).grid(
                row=row, column=0, sticky="w", padx=(0, 20), pady=6
            )
            labels = [item[0] for item in options]
            values = [item[1] for item in options]
            combo = ttk.Combobox(
                body,
                state="readonly",
                values=labels,
                width=24,
                style="NP.TCombobox",
                font=("Segoe UI", 10),
            )
            current = getattr(self.settings, key)
            combo.current(values.index(current) if current in values else 0)
            combo.grid(row=row, column=1, sticky="ew", pady=6)
            combo.bind("<<ComboboxSelected>>", lambda _e: self.change(key, values[combo.current()]))
            row += 1

        select(
            "Theme",
            "theme",
            [("Follow Windows", "system"), ("Midnight", "dark"), ("Daylight", "light")],
        )
        select(
            "Accent",
            "accent",
            [("Mint", "mint"), ("Sky", "blue"), ("Lavender", "violet"), ("Peach", "peach")],
        )
        select(
            "Widget size",
            "size",
            [
                ("Mini · just the essentials", "mini"),
                ("Compact", "compact"),
                ("Comfortable · larger text", "comfortable"),
            ],
        )
        tk.Label(body, text="Corner radius", bg=c["bg"], fg=c["text"], font=("Segoe UI", 10)).grid(
            row=row, column=0, sticky="w", padx=(0, 20), pady=6
        )
        radius_control = tk.Frame(body, bg=c["bg"])
        radius_control.grid(row=row, column=1, sticky="ew", pady=6)
        radius_text = tk.StringVar(value=f"{self.settings.corner_radius} px")
        tk.Label(
            radius_control,
            textvariable=radius_text,
            width=5,
            anchor="e",
            bg=c["bg"],
            fg=c["muted"],
            font=("Segoe UI", 9),
        ).pack(side="right")

        def set_radius(value):
            radius = int(float(value))
            radius_text.set(f"{radius} px")
            if radius != self.settings.corner_radius:
                self.change("corner_radius", radius)

        radius_slider = tk.Scale(
            radius_control,
            from_=0,
            to=24,
            orient="horizontal",
            resolution=1,
            showvalue=False,
            length=140,
            sliderlength=16,
            width=12,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=c["edge"],
            highlightcolor=c["accent"],
            bg=c["bg"],
            troughcolor=c["card"],
            activebackground=c["accent"],
            relief="flat",
            cursor="hand2",
            takefocus=True,
        )
        radius_slider.set(self.settings.corner_radius)
        radius_slider.configure(command=set_radius)
        radius_slider.pack(side="left", fill="x", expand=True)
        row += 1
        select(
            "Speed units",
            "units",
            [("Bits per second · Mbps", "bits"), ("Bytes per second · MB/s", "bytes")],
        )
        select(
            "Refresh",
            "interval",
            [
                ("Every 0.5 seconds", 0.5),
                ("Every second", 1.0),
                ("Every 2 seconds", 2.0),
                ("Every 3 seconds", 3.0),
            ],
        )
        select(
            "Opacity", "opacity", [("100% · solid", 1.0), ("90%", 0.9), ("80%", 0.8), ("65%", 0.65)]
        )
        options = [("Auto · physical adapters", "auto")]
        options.extend(
            (a.name + ("" if a.is_up else " (disconnected)"), a.id)
            for a in self.adapters
            if not a.loopback
        )
        if self.settings.adapter not in [value for _, value in options]:
            options.append(("Saved adapter (unavailable)", self.settings.adapter))
        select("Network adapter", "adapter", options)
        for label, key in (("Always on top", "topmost"), ("Show activity graphs", "graphs")):
            var = tk.BooleanVar(value=getattr(self.settings, key))
            check = tk.Checkbutton(
                body,
                text=label,
                variable=var,
                bg=c["bg"],
                fg=c["text"],
                selectcolor=c["card"],
                activebackground=c["bg"],
                activeforeground=c["text"],
                font=("Segoe UI", 10),
                anchor="w",
                highlightthickness=0,
                command=lambda k=key, v=var: self.change(k, v.get()),
            )
            check.var = var
            check.grid(row=row, column=0, columnspan=2, sticky="w", pady=3)
            row += 1
        message = (
            "Cannot save preferences in this location."
            if self.save_error
            else "Changes apply instantly and are saved automatically."
        )
        tk.Label(
            body,
            text=message + "\nDrag the widget to move it. Right-click for quick options.",
            font=("Segoe UI", 9),
            justify="left",
            bg=c["bg"],
            fg=c["muted"],
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(14, 16))
        row += 1
        actions = tk.Frame(body, bg=c["bg"])
        actions.grid(row=row, column=0, columnspan=2, sticky="ew")
        self._button(actions, "Reset defaults", self.reset_style, False).pack(side="left")
        self._button(actions, "Help", self.show_help, False).pack(side="left", padx=8)
        self._button(actions, "Done", self.dismiss, True).pack(side="right")

    def _button(self, parent, label, command, primary):
        c = self.colors
        return tk.Button(
            parent,
            text=label,
            command=command,
            cursor="hand2",
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
            font=("Segoe UI", 10, "bold" if primary else "normal"),
            bg=c["accent"] if primary else c["card"],
            fg=("#111827" if self.theme == "dark" else "#FFFFFF") if primary else c["text"],
            activebackground=c["hover"],
            activeforeground=c["text"],
        )

    def reset_style(self):
        reset_appearance(self.settings)
        self.change("theme", self.settings.theme)
        self.root.after_cancel(self.timer)
        self._poll()

    def show_help(self):
        messagebox.showinfo(
            "About NetPulse",
            "NETPULSE 1.0\n\n"
            "Drag anywhere on the widget to move it. Use the sliders icon or right-click to customize. "
            "The × button closes it. Ctrl+, opens settings; Ctrl+Q exits.\n\n"
            "Rates show actual network traffic during each measured interval, not your broadband plan "
            "or maximum connection speed. Local-network transfers also count. Zero while idle is normal.\n\n"
            "Auto adds connected physical adapters and excludes virtual/VPN interfaces to avoid counting "
            "traffic twice. For a VPN-only or virtual machine setup, choose a specific adapter. "
            "A connected adapter does not guarantee Internet access.\n\n"
            "Mbps = megabits/second; MB/s = megabytes/second. 8 Mbps = 1 MB/s. "
            "Graphs use their own changing scale and show the last 48 readings.\n\n"
            "No accounts, telemetry, speed-test traffic, or administrator access. "
            "Preferences are stored locally in %LOCALAPPDATA%\\NetPulse.",
            parent=self.dialog or self.root,
        )

    def close(self):
        self.persist()
        self._hide_tip()
        for timer in (self.timer, self.theme_timer):
            if timer is not None:
                self.root.after_cancel(timer)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="NetPulse — live network traffic in a tiny window")
    parser.add_argument("--config", type=Path, help="Optional preferences path")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("NetPulse currently supports Windows only.")
    enable_dpi_awareness()
    mutex = single_instance()
    if mutex is None:
        ctypes.windll.user32.MessageBoxW(
            None,
            "NetPulse is already running. Look for its small desktop widget.",
            "NetPulse",
            0x40,
        )
        return
    root = tk.Tk()
    try:
        NetPulse(root, args.config)
        root.mainloop()
    except Exception as error:
        messagebox.showerror("NetPulse could not start", str(error), parent=root)
        root.destroy()
        raise


if __name__ == "__main__":
    main()

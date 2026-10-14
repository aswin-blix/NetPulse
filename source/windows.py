"""Small Windows integrations; no registry writes or elevated permissions."""

from __future__ import annotations

import ctypes as c
import sys
from ctypes import wintypes as w


def enable_dpi_awareness() -> None:
    if sys.platform == "win32":
        try:
            c.windll.user32.SetProcessDpiAwarenessContext(c.c_void_p(-4))
        except (AttributeError, OSError):
            c.windll.user32.SetProcessDPIAware()


def system_theme() -> str:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
    except (ImportError, OSError):
        return "dark"


class MonitorInfo(c.Structure):
    _fields_ = [
        ("cbSize", w.DWORD),
        ("rcMonitor", w.RECT),
        ("rcWork", w.RECT),
        ("dwFlags", w.DWORD),
    ]


def work_areas() -> list[tuple[int, int, int, int]]:
    if sys.platform != "win32":
        return []
    areas = []
    callback_type = c.WINFUNCTYPE(w.BOOL, w.HMONITOR, w.HDC, c.POINTER(w.RECT), w.LPARAM)
    user = c.windll.user32
    user.GetMonitorInfoW.argtypes = [w.HMONITOR, c.POINTER(MonitorInfo)]

    @callback_type
    def callback(monitor, _hdc, _rect, _data):
        info = MonitorInfo(cbSize=c.sizeof(MonitorInfo))
        if user.GetMonitorInfoW(monitor, c.byref(info)):
            r = info.rcWork
            areas.append((r.left, r.top, r.right, r.bottom))
        return True

    user.EnumDisplayMonitors(None, None, callback, 0)
    return areas


def clamp_position(
    x: int, y: int, width: int, height: int, areas: list[tuple[int, int, int, int]]
) -> tuple[int, int]:
    if not areas:
        return x, y

    def candidate(area):
        left, top, right, bottom = area
        return max(left, min(x, right - width)), max(top, min(y, bottom - height))

    return min((candidate(a) for a in areas), key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2)


def native_handle(root) -> int:
    user = c.windll.user32
    user.GetAncestor.argtypes = [w.HWND, w.UINT]
    user.GetAncestor.restype = w.HWND
    return user.GetAncestor(root.winfo_id(), 2) or root.winfo_id()


def move_window(root, x: int, y: int) -> None:
    if sys.platform == "win32":
        user = c.windll.user32
        user.SetWindowPos.argtypes = [w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT]
        user.SetWindowPos(native_handle(root), None, x, y, 0, 0, 0x0015)
    else:
        root.geometry(f"+{max(0, x)}+{max(0, y)}")


def style_window(root, width: int, height: int, radius: int) -> None:
    """Apply the actual corner radius in pixels; zero restores square corners."""
    if sys.platform != "win32":
        return
    gdi, user = c.windll.gdi32, c.windll.user32
    gdi.CreateRoundRectRgn.argtypes = [c.c_int] * 6
    gdi.CreateRoundRectRgn.restype = w.HRGN
    gdi.DeleteObject.argtypes = [w.HGDIOBJ]
    user.SetWindowRgn.argtypes = [w.HWND, w.HRGN, w.BOOL]
    if radius <= 0:
        user.SetWindowRgn(native_handle(root), None, True)
        return
    # Win32 takes the corner ellipse's diameter, not its radius.
    diameter = 2 * min(radius, width // 2, height // 2)
    region = gdi.CreateRoundRectRgn(0, 0, width + 1, height + 1, diameter, diameter)
    if region and not user.SetWindowRgn(native_handle(root), region, True):
        gdi.DeleteObject(region)


def single_instance() -> object | None:
    """Hold one widget per Windows session; return None for an existing instance."""
    if sys.platform != "win32":
        return object()
    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [c.c_void_p, w.BOOL, w.LPCWSTR]
    kernel.CreateMutexW.restype = w.HANDLE
    handle = kernel.CreateMutexW(None, False, "Local\\NetPulse.Widget.v1")
    if c.get_last_error() == 183:
        kernel.CloseHandle.argtypes = [w.HANDLE]
        kernel.CloseHandle(handle)
        return None
    return handle or object()

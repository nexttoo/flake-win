"""Тонкая обёртка над Win32/DWM: окна, мониторы, панель задач, курсор.

Всё возвращается в ФИЗИЧЕСКИХ пикселях — перевод в логические координаты Qt
делает модуль world.py.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
shcore = ctypes.WinDLL("shcore", use_last_error=True)

GWL_STYLE = -16
GWL_EXSTYLE = -20

WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

WS_CHILD = 0x40000000
WS_DISABLED = 0x08000000

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

ABM_GETSTATE = 0x00000004
ABS_AUTOHIDE = 0x00000001

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02


def _proto(fn, restype, *argtypes):
    fn.restype = restype
    fn.argtypes = list(argtypes)
    return fn


GetWindowLongPtrW = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
SetWindowLongPtrW = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)

_proto(GetWindowLongPtrW, ctypes.c_ssize_t, wt.HWND, ctypes.c_int)
_proto(SetWindowLongPtrW, ctypes.c_ssize_t, wt.HWND, ctypes.c_int, ctypes.c_ssize_t)
_proto(user32.GetWindowRect, wt.BOOL, wt.HWND, ctypes.POINTER(wt.RECT))
_proto(user32.IsWindowVisible, wt.BOOL, wt.HWND)
_proto(user32.IsIconic, wt.BOOL, wt.HWND)
_proto(user32.GetWindowThreadProcessId, wt.DWORD, wt.HWND, ctypes.POINTER(wt.DWORD))
_proto(user32.GetWindowTextLengthW, ctypes.c_int, wt.HWND)
_proto(user32.GetWindowTextW, ctypes.c_int, wt.HWND, wt.LPWSTR, ctypes.c_int)
_proto(user32.GetClassNameW, ctypes.c_int, wt.HWND, wt.LPWSTR, ctypes.c_int)
_proto(user32.GetCursorPos, wt.BOOL, ctypes.POINTER(wt.POINT))
_proto(user32.GetAsyncKeyState, ctypes.c_short, ctypes.c_int)
_proto(user32.FindWindowW, wt.HWND, wt.LPCWSTR, wt.LPCWSTR)
_proto(user32.GetForegroundWindow, wt.HWND)
_proto(dwmapi.DwmGetWindowAttribute, ctypes.c_long, wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD)


# --------------------------------------------------------------------------- #
#  Окна
# --------------------------------------------------------------------------- #

WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def enum_windows() -> list[int]:
    """Все top-level окна (включая невидимые — фильтруем отдельно)."""
    handles: list[int] = []

    def _cb(hwnd, _lparam):
        handles.append(hwnd)
        return True

    proc = WNDENUMPROC(_cb)
    user32.EnumWindows(proc, 0)
    return handles


def ex_style(hwnd: int) -> int:
    return int(GetWindowLongPtrW(wt.HWND(hwnd), GWL_EXSTYLE)) & 0xFFFFFFFF


def style(hwnd: int) -> int:
    return int(GetWindowLongPtrW(wt.HWND(hwnd), GWL_STYLE)) & 0xFFFFFFFF


def add_ex_style(hwnd: int, flags: int) -> None:
    cur = int(GetWindowLongPtrW(wt.HWND(hwnd), GWL_EXSTYLE))
    SetWindowLongPtrW(wt.HWND(hwnd), GWL_EXSTYLE, cur | flags)


def window_rect(hwnd: int):
    r = wt.RECT()
    if not user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(r)):
        return None
    return (r.left, r.top, r.right, r.bottom)


def extended_frame_bounds(hwnd: int):
    """Видимые границы окна (Windows 10+): без прозрачной рамки ресайза."""
    r = wt.RECT()
    hr = dwmapi.DwmGetWindowAttribute(
        wt.HWND(hwnd),
        DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(r),
        ctypes.sizeof(r),
    )
    if hr != 0:
        return None
    if r.right - r.left < 1 or r.bottom - r.top < 1:
        return None
    return (r.left, r.top, r.right, r.bottom)


def is_cloaked(hwnd: int) -> bool:
    """Скрытые UWP-«призраки» и окна на других виртуальных рабочих столах."""
    value = wt.DWORD(0)
    hr = dwmapi.DwmGetWindowAttribute(
        wt.HWND(hwnd),
        DWMWA_CLOAKED,
        ctypes.byref(value),
        ctypes.sizeof(value),
    )
    return hr == 0 and value.value != 0


def class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(wt.HWND(hwnd), buf, 256)
    return buf.value


def window_title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(wt.HWND(hwnd))
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 2)
    user32.GetWindowTextW(wt.HWND(hwnd), buf, n + 2)
    return buf.value


def window_pid(hwnd: int) -> int:
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(wt.HWND(hwnd), ctypes.byref(pid))
    return int(pid.value)


# --------------------------------------------------------------------------- #
#  Мониторы
# --------------------------------------------------------------------------- #

class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("rcMonitor", wt.RECT),
        ("rcWork", wt.RECT),
        ("dwFlags", wt.DWORD),
    ]


MONITORENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC,
                                     ctypes.POINTER(wt.RECT), wt.LPARAM)


_proto(user32.EnumDisplayMonitors, wt.BOOL, wt.HDC, ctypes.POINTER(wt.RECT),
       MONITORENUMPROC, wt.LPARAM)
_proto(user32.GetMonitorInfoW, wt.BOOL, wt.HMONITOR, ctypes.POINTER(MONITORINFO))


@dataclass(frozen=True)
class MonitorRect:
    left: int
    top: int
    right: int
    bottom: int
    work_left: int
    work_top: int
    work_right: int
    work_bottom: int
    primary: bool

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> tuple[float, float]:
        return ((self.left + self.right) * 0.5, (self.top + self.bottom) * 0.5)


def enum_monitors() -> list[MonitorRect]:
    out: list[MonitorRect] = []

    def _cb(hmon, _hdc, _rect, _lparam):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            m = info.rcMonitor
            w = info.rcWork
            out.append(MonitorRect(
                m.left, m.top, m.right, m.bottom,
                w.left, w.top, w.right, w.bottom,
                bool(info.dwFlags & 1),
            ))
        return True

    proc = MONITORENUMPROC(_cb)
    user32.EnumDisplayMonitors(None, None, proc, 0)
    return out


def dpi_for_point(x: int, y: int) -> float:
    """Эффективный DPI монитора под точкой (fallback 96)."""
    pt = wt.POINT(int(x), int(y))
    try:
        monitor = user32.MonitorFromPoint(pt, 2)  # MONITOR_DEFAULTTONEAREST
        dpi_x = wt.UINT(96)
        dpi_y = wt.UINT(96)
        if shcore.GetDpiForMonitor(monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
            return max(0.5, dpi_x.value / 96.0)
    except Exception:
        pass
    return 1.0


# --------------------------------------------------------------------------- #
#  Панель задач (аналог Dock)
# --------------------------------------------------------------------------- #

class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", wt.HWND),
        ("uCallbackMessage", wt.UINT),
        ("uEdge", wt.UINT),
        ("rc", wt.RECT),
        ("lParam", wt.LPARAM),
    ]


_proto(shell32.SHAppBarMessage, ctypes.c_size_t, wt.DWORD, ctypes.POINTER(APPBARDATA))


def taskbar_rect():
    """Прямоугольник панели задач, если она видима и не автоскрыта."""
    hwnd = user32.FindWindowW("Shell_TrayWnd", None)
    if not hwnd:
        return None
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    state = shell32.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(abd))
    if state & ABS_AUTOHIDE:
        return None
    rect = window_rect(hwnd)
    if not rect:
        return None
    l, t, r, b = rect
    if r - l < 40 or b - t < 12:
        return None
    return rect


# --------------------------------------------------------------------------- #
#  Ввод
# --------------------------------------------------------------------------- #

def cursor_pos() -> tuple[int, int]:
    p = wt.POINT()
    if not user32.GetCursorPos(ctypes.byref(p)):
        return (0, 0)
    return (p.x, p.y)


def key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0)

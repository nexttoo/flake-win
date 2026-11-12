"""Отслеживание окон Windows: где могут расти сугробы и что непроницаемо.

Координатная система — логическая, ось Y вниз (как в Qt).
Сугроб лежит НА верхней кромке окна и растёт вверх (в сторону меньшего Y).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QRect, QRectF

from . import winapi
from .world import World

# Окна, которые не являются «мебелью» рабочего стола.
_SKIP_CLASSES = {
    "progman", "workerw", "shell_traywnd", "shell_secondarytraywnd",
    "windows.ui.core.corewindow", "applicationframewindow",
    "windowsdashboard", "xaml_diagnostics_agent_wnd", "ime",
    "msctfime ui", "default ime", "tooltips_class32", "sysshadow",
}

_TOOLTIP_HINTS = ("tooltip", "popup", "menu", "ime", "overlay")


@dataclass
class Ledge:
    """Кромка, на которой может лежать снег."""
    id: str
    x: float
    top: float
    width: float
    z: int
    is_taskbar: bool = False
    can_accumulate: bool = True

    @property
    def right(self) -> float:
        return self.x + self.width


@dataclass
class Occluder:
    """Твёрдое тело окна — снежок отскакивает, снежинка отталкивается."""
    id: str
    x: float
    top: float
    right: float
    bottom: float
    z: int
    is_taskbar: bool = False

    @property
    def width(self) -> float:
        return self.right - self.x

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass
class Snapshot:
    ledges: list[Ledge] = field(default_factory=list)
    occluders: list[Occluder] = field(default_factory=list)
    blocked: list[QRectF] = field(default_factory=list)
    foreground: int = 0
    signature: tuple = ()


class WindowTracker:
    def __init__(self, world: World) -> None:
        self.world = world
        self._snapshot = Snapshot()
        self._last_poll = 0.0
        self._last_fg = 0
        self._own_pid = os.getpid()
        # True — снег прячется над развёрнутым окном (как в macOS-оригинале).
        self.hide_maximized = False

    # ------------------------------------------------------------------ #
    def snapshot(self, force: bool = False, active: bool = False) -> Snapshot:
        now = time.perf_counter()
        fg = winapi.foreground_window()
        interval = 1.0 / 30.0 if active else 1.0 / 10.0
        if not force and fg == self._last_fg and (now - self._last_poll) < interval:
            return self._snapshot
        self._last_fg = fg
        self._last_poll = now
        self._snapshot = self._poll(fg)
        return self._snapshot

    # ------------------------------------------------------------------ #
    def _poll(self, fg: int) -> Snapshot:
        world = self.world
        ledges: list[Ledge] = []
        occluders: list[Occluder] = []
        blocked: list[QRectF] = []

        monitors = winapi.enum_monitors()
        raw: list[tuple] = []

        for z, hwnd in enumerate(winapi.enum_windows()):
            if winapi.window_pid(hwnd) == self._own_pid:
                continue
            if not winapi.user32.IsWindowVisible(winapi.wt.HWND(hwnd)):
                continue
            if winapi.user32.IsIconic(winapi.wt.HWND(hwnd)):
                continue
            if winapi.is_cloaked(hwnd):
                continue

            cls = winapi.class_name(hwnd).lower()
            if cls in _SKIP_CLASSES:
                continue
            if any(hint in cls for hint in _TOOLTIP_HINTS) and "window" not in cls:
                continue

            ex = winapi.ex_style(hwnd)
            if ex & winapi.WS_EX_TOOLWINDOW:
                continue

            title = winapi.window_title(hwnd)
            has_caption = bool(winapi.style(hwnd) & 0x00C00000)  # WS_CAPTION
            if not title and not has_caption:
                continue

            bounds = winapi.extended_frame_bounds(hwnd) or winapi.window_rect(hwnd)
            if not bounds:
                continue
            logical = world.rect_to_logical(*bounds)
            if logical is None:
                continue
            if logical.width() < 60 or logical.height() < 40:
                continue

            raw.append((hwnd, z, logical, bool(ex & winapi.WS_EX_TOPMOST), monitors))

        # Развёрнутые/полноэкранные окна — отдельно: они либо прячут снег,
        # либо просто игнорируются, но в любом случае не «вложены» в других.
        maximized_ids: set[int] = set()
        for hwnd, z, rect, topmost, mons in raw:
            if self._covers_monitor(rect, mons, world):
                maximized_ids.add(hwnd)
                if self.hide_maximized:
                    blocked.append(QRectF(rect))

        for hwnd, z, rect, topmost, mons in raw:
            if hwnd in maximized_ids:
                # Иначе снег идёт поверх развёрнутого окна,
                # а копится на панели задач.
                continue

            # «Вложено» = окно целиком лежит на другом окне, которое ВПЕРЕДИ
            # (меньший z). Окно на фоне другого — не дочернее.
            is_nested = any(
                oh != hwnd
                and oh not in maximized_ids
                and oz < z
                and other.width() * other.height() > rect.width() * rect.height() * 1.05
                and rect.left() >= other.left() - 2
                and rect.right() <= other.right() + 2
                and rect.top() >= other.top() - 2
                and rect.bottom() <= other.bottom() + 2
                for oh, oz, other, ot, om in raw
            )

            oid = f"w{hwnd}"
            occluders.append(Occluder(oid, rect.left(), rect.top(),
                                      rect.right(), rect.bottom(), z))

            can = (
                not topmost
                and not is_nested
                and rect.height() >= 100
                and rect.width() >= 220
                and not self._near_fullscreen(rect, mons, world)
            )
            ledges.append(Ledge(oid, rect.left(), rect.top(), rect.width(), z,
                                is_taskbar=False, can_accumulate=can))

        # Панель задач — аналог Dock: на её верхней кромке копится снег.
        bar = winapi.taskbar_rect()
        if bar:
            logical = world.rect_to_logical(*bar)
            if logical and logical.height() < logical.width() * 0.6:
                lid = "taskbar"
                ledges.append(Ledge(lid, logical.left(), logical.top(),
                                    logical.width(), -1000, is_taskbar=True))
                occluders.append(Occluder(lid, logical.left(), logical.top(),
                                          logical.right(), logical.bottom(),
                                          -1000, is_taskbar=True))

        signature = tuple(sorted(
            (lg.id, round(lg.x, 1), round(lg.top, 1), round(lg.width, 1))
            for lg in ledges
        ))
        return Snapshot(ledges, occluders, blocked, fg, signature)

    # ------------------------------------------------------------------ #
    def _covers_monitor(self, rect: QRect, monitors, world: World) -> bool:
        """Окно во весь экран или во всю рабочую область -> снег прячется."""
        screen = world.screen_at(rect.center().x(), rect.center().y())
        mon = None
        for m in monitors:
            l = world.rect_to_logical(m.left, m.top, m.right, m.bottom)
            if l and l.contains(rect.center()):
                mon = (l, world.rect_to_logical(m.work_left, m.work_top,
                                                m.work_right, m.work_bottom))
                break
        if mon is None and screen is not None:
            mon = (QRectF(screen.logical), QRectF(screen.logical))
        if mon is None:
            return False

        full, work = mon
        for area in (work, full):
            if area is None or area.width() < 10 or area.height() < 10:
                continue
            if (rect.left() <= area.left() + 10
                    and rect.right() >= area.right() - 10
                    and rect.top() <= area.top() + 10
                    and rect.bottom() >= area.bottom() - 10):
                return True
        return False

    def _near_fullscreen(self, rect: QRect, monitors, world: World) -> bool:
        for m in monitors:
            area = world.rect_to_logical(m.left, m.top, m.right, m.bottom)
            if area is None or area.width() < 10:
                continue
            if not area.contains(rect.center()):
                continue
            if rect.width() >= area.width() * 0.94 and rect.height() >= area.height() * 0.90:
                return True
        return False

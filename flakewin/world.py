"""Экраны и перевод координат: физические пиксели Win32 <-> логические Qt."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QGuiApplication

from . import winapi


@dataclass(frozen=True)
class Screen:
    index: int
    name: str
    logical: QRect          # координаты Qt (device independent)
    dpr: float              # масштаб Windows (1.0 = 100%, 1.5 = 150% ...)
    physical: QRect         # координаты Win32 (пиксели)

    @property
    def work(self) -> QRect:
        """Рабочая область (без панели задач) в логических координатах."""
        return self.logical


class World:
    """Набор экранов + преобразование координат."""

    def __init__(self) -> None:
        self.screens: list[Screen] = []
        self.refresh()

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        monitors = winapi.enum_monitors()
        screens: list[Screen] = []
        for index, qscreen in enumerate(QGuiApplication.screens()):
            g = qscreen.geometry()
            dpr = float(qscreen.devicePixelRatio()) or 1.0
            cand_cx = (g.x() + g.width() * 0.5) * dpr
            cand_cy = (g.y() + g.height() * 0.5) * dpr

            best = None
            best_d = None
            for m in monitors:
                dx = m.center[0] - cand_cx
                dy = m.center[1] - cand_cy
                d = dx * dx + dy * dy
                if best_d is None or d < best_d:
                    best_d = d
                    best = m
            if best is not None:
                phys = QRect(best.left, best.top, best.width, best.height)
                dpr = max(0.5, (best.width / g.width()) if g.width() else dpr)
            else:
                phys = QRect(round(g.x() * dpr), round(g.y() * dpr),
                             round(g.width() * dpr), round(g.height() * dpr))
            screens.append(Screen(index, qscreen.name(), QRect(g), dpr, phys))
        self.screens = screens

    # ------------------------------------------------------------------ #
    def bounds(self) -> QRect:
        if not self.screens:
            return QRect(0, 0, 1920, 1080)
        r = QRect(self.screens[0].logical)
        for s in self.screens[1:]:
            r = r.united(s.logical)
        return r

    def screen_at(self, x: float, y: float) -> Screen | None:
        for s in self.screens:
            if s.logical.left() <= x <= s.logical.right() and \
                    s.logical.top() <= y <= s.logical.bottom():
                return s
        return None

    def to_logical(self, px: float, py: float) -> tuple[float, float]:
        """Физическая точка Win32 -> логическая точка Qt."""
        for s in self.screens:
            p = s.physical
            if p.left() <= px <= p.right() and p.top() <= py <= p.bottom():
                return (
                    s.logical.left() + (px - p.left()) / s.dpr,
                    s.logical.top() + (py - p.top()) / s.dpr,
                )
        # Вне всех мониторов — берём ближайший.
        best = None
        best_d = None
        for s in self.screens:
            p = s.physical
            dx = px - (p.left() + p.width() * 0.5)
            dy = py - (p.top() + p.height() * 0.5)
            d = dx * dx + dy * dy
            if best_d is None or d < best_d:
                best_d, best = d, s
        if best is None:
            return (px, py)
        p = best.physical
        return (
            best.logical.left() + (px - p.left()) / best.dpr,
            best.logical.top() + (py - p.top()) / best.dpr,
        )

    def rect_to_logical(self, l: float, t: float, r: float, b: float) -> QRectF | None:
        """Физический прямоугольник Win32 -> логический прямоугольник Qt."""
        s = self._screen_for_physical_rect(l, t, r, b)
        if s is None:
            return None
        p = s.physical
        return QRectF(
            s.logical.left() + (l - p.left()) / s.dpr,
            s.logical.top() + (t - p.top()) / s.dpr,
            (r - l) / s.dpr,
            (b - t) / s.dpr,
        )

    def _screen_for_physical_rect(self, l: float, t: float, r: float, b: float) -> Screen | None:
        cx = (l + r) * 0.5
        cy = (t + b) * 0.5
        for s in self.screens:
            p = s.physical
            if p.left() <= cx <= p.right() and p.top() <= cy <= p.bottom():
                return s
        best, best_d = None, None
        for s in self.screens:
            p = s.physical
            dx = cx - (p.left() + p.width() * 0.5)
            dy = cy - (p.top() + p.height() * 0.5)
            d = dx * dx + dy * dy
            if best_d is None or d < best_d:
                best_d, best = d, s
        return best

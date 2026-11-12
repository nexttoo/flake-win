"""Прозрачные оверлеи на каждом мониторе + главный цикл симуляции."""
from __future__ import annotations

import math
import time
from collections import deque

from PySide6.QtCore import QObject, QRectF, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from . import winapi
from .render import Renderer
from .settings import Settings
from .sim import Simulator
from .tracker import WindowTracker
from .world import Screen, World


class SnowOverlay(QWidget):
    """Слой снега над одним монитором: прозрачный, поверх окон, без кликов."""

    def __init__(self, engine: "OverlayEngine", screen: Screen) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.engine = engine
        self.screen = screen
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle("Flake")
        self.setGeometry(screen.logical)
        self._apply_native_styles()

    # ------------------------------------------------------------------ #
    def _apply_native_styles(self) -> None:
        hwnd = int(self.winId())
        try:
            winapi.add_ex_style(
                hwnd,
                winapi.WS_EX_LAYERED | winapi.WS_EX_TRANSPARENT
                | winapi.WS_EX_TOOLWINDOW | winapi.WS_EX_NOACTIVATE
                | winapi.WS_EX_TOPMOST,
            )
        except Exception:
            pass

    def show_overlay(self) -> None:
        self.setGeometry(self.screen.logical)
        self.show()
        self._apply_native_styles()

    # ------------------------------------------------------------------ #
    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        origin = self.screen.logical
        p.translate(-origin.left(), -origin.top())
        rect = QRectF(origin)
        self.engine.renderer.draw(p, self.engine.sim, self.screen.dpr, rect)
        p.end()


class OverlayEngine(QObject):
    """Владеет симуляцией, оверлеями и таймером кадров."""

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.world = World()
        self.tracker = WindowTracker(self.world)
        self.tracker.hide_maximized = bool(settings["hide_on_maximized"])
        self.sim = Simulator(self.world, self.tracker, settings)
        self.sim.train_runner.enabled = bool(settings["train_enabled"])
        try:
            from .sim import Snowman

            Snowman.SCALE = max(0.6, min(3.0, float(settings["snowman_scale"])))
        except Exception:
            pass
        self.renderer = Renderer()

        self.overlays: list[SnowOverlay] = []
        self._fps = int(settings["fps_limit"] or 30)
        self._frame_time = 1.0 / max(10, min(60, self._fps))
        self._last = time.perf_counter()
        self._cursor_hist: deque[tuple[float, float, float]] = deque(maxlen=12)
        self._last_mouse = (-10000.0, -10000.0)
        self._mouse_move_age = 0.0

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(int(1000.0 / max(10, min(60, self._fps))))
        self.timer.timeout.connect(self.tick)

        app = QGuiApplication.instance()
        if app is not None:
            app.screenAdded.connect(lambda _s: self.rebuild())
            app.screenRemoved.connect(lambda _s: self.rebuild())
            app.primaryScreenChanged.connect(lambda _s: self.rebuild())
            for screen in QGuiApplication.screens():
                screen.geometryChanged.connect(lambda *_a: self.rebuild())

        self.sim.on_toast = self._on_toast
        self.on_toast = None

    # ------------------------------------------------------------------ #
    def _on_toast(self, text: str) -> None:
        if self.on_toast is not None:
            self.on_toast(text)

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        self.build_overlays()
        self._last = time.perf_counter()
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()
        for overlay in self.overlays:
            overlay.hide()
            overlay.deleteLater()
        self.overlays.clear()

    def rebuild(self) -> None:
        for overlay in self.overlays:
            overlay.hide()
            overlay.deleteLater()
        self.overlays.clear()
        self.world.refresh()
        self.build_overlays()

    def build_overlays(self) -> None:
        self.world.refresh()
        for screen in self.world.screens:
            overlay = SnowOverlay(self, screen)
            overlay.show_overlay()
            self.overlays.append(overlay)

    # ------------------------------------------------------------------ #
    def set_intensity(self, value: float) -> None:
        self.settings["intensity"] = value
        self.sim.set_intensity(value)

    def set_paused(self, value: bool) -> None:
        self.settings["paused"] = value
        self.sim.paused = value

    def set_mouse_enabled(self, value: bool) -> None:
        self.settings["mouse_enabled"] = value
        self.sim.mouse_enabled = value

    def set_hide_maximized(self, value: bool) -> None:
        self.settings["hide_on_maximized"] = bool(value)
        self.tracker.hide_maximized = bool(value)
        self.tracker._last_poll = 0.0
        self.tracker.snapshot(force=True)

    def clear(self) -> None:
        self.sim.clear()

    def melt(self) -> None:
        self.sim.clear()

    # ------------------------------------------------------------------ #
    def tick(self) -> None:
        now = time.perf_counter()
        # Чем больше снега, тем дешевле кадр: снег медленный, реже — не заметно.
        count = self.sim.field.count
        if count >= 2000:
            fps = 20.0
        elif count >= 1200:
            fps = 24.0
        else:
            fps = 30.0
        fps = min(fps, float(self._fps))
        self._frame_time = 1.0 / max(12.0, fps)
        dt = now - self._last
        if dt < self._frame_time * 0.72:
            return
        self._last = now
        dt = min(dt, 0.12)

        self._sample_pointer(now, dt)
        self.sim.update(dt, active=self._mouse_move_age < 0.35)

        for overlay in self.overlays:
            overlay.update()

    def _sample_pointer(self, now: float, dt: float) -> None:
        px, py = winapi.cursor_pos()
        lx, ly = self.world.to_logical(px, py)

        if abs(lx - self._last_mouse[0]) + abs(ly - self._last_mouse[1]) > 0.4:
            self._mouse_move_age = 0.0
        else:
            self._mouse_move_age += dt
        self._last_mouse = (lx, ly)

        self._cursor_hist.append((now, lx, ly))
        vx = vy = 0.0
        if len(self._cursor_hist) >= 2:
            t0, x0, y0 = self._cursor_hist[0]
            span = max(0.016, now - t0)
            if len(self._cursor_hist) >= 2:
                vx = (lx - x0) / span
                vy = (ly - y0) / span
        # Сглаживание, чтобы «флик» не прыгал.
        sim = self.sim
        sim.mouse_vx = sim.mouse_vx * 0.55 + vx * 0.45
        sim.mouse_vy = sim.mouse_vy * 0.55 + vy * 0.45
        sim.mouse_x = lx
        sim.mouse_y = ly

        # Скорость для броска: средняя за последние ~90 мс.
        fx = fy = 0.0
        window = [h for h in self._cursor_hist if now - h[0] <= 0.09]
        if len(window) >= 2:
            t0, x0, y0 = window[0]
            span = max(0.016, now - t0)
            fx = (lx - x0) / span
            fy = (ly - y0) / span
        still = math.hypot(vx, vy) < 40.0
        if still:
            sim.flick_vx *= 0.6
            sim.flick_vy *= 0.6
        else:
            sim.flick_vx = fx
            sim.flick_vy = fy

        sim.mouse_down = winapi.key_down(winapi.VK_LBUTTON)
        sim.right_down = winapi.key_down(winapi.VK_RBUTTON)

    # ------------------------------------------------------------------ #
    def set_visible(self, visible: bool) -> None:
        for overlay in self.overlays:
            overlay.setVisible(visible)

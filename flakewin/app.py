"""Flake для Windows — точка входа: трей, меню, диалоги."""
from __future__ import annotations

import ctypes
import os
import random
import sys

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QIcon, QImage,
                           QPainter, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QApplication, QInputDialog, QMenu, QSystemTrayIcon

from .overlay import OverlayEngine
from .settings import Settings
from .sim import Snowman

INTENSITY_PRESETS = (
    ("Мало", 0.35),
    ("Средне", 0.7),
    ("Много", 1.0),
    ("Метель", 1.4),
)

MUTEX_NAME = "Global\\FlakeWinSingleInstance"


# --------------------------------------------------------------------------- #
#  Иконка
# --------------------------------------------------------------------------- #

def make_snowflake_image(size: int = 64) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    c = size / 2.0

    glow = QRadialGradient(c, c, c)
    glow.setColorAt(0.0, QColor(255, 255, 255, 235))
    glow.setColorAt(0.55, QColor(206, 228, 255, 170))
    glow.setColorAt(1.0, QColor(180, 210, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(QPointF(c, c), c - 1, c - 1)

    pen = QPen(QColor(28, 74, 136, 235))
    pen.setWidthF(max(1.6, size * 0.075))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    r = c * 0.82
    import math
    for k in range(6):
        a = k * math.pi / 3.0
        dx, dy = math.cos(a), math.sin(a)
        p.drawLine(QPointF(c, c), QPointF(c + dx * r, c + dy * r))
        for t in (0.58, 0.78):
            bx, by = c + dx * r * t, c + dy * r * t
            for sign in (1.0, -1.0):
                ba = a + sign * 0.7
                ln = r * 0.30
                p.drawLine(QPointF(bx, by),
                           QPointF(bx + math.cos(ba) * ln, by + math.sin(ba) * ln))
    p.end()
    return img


def make_snowflake_icon(size: int = 64) -> QIcon:
    return QIcon(QPixmap.fromImage(make_snowflake_image(size)))


# --------------------------------------------------------------------------- #
#  Автозапуск
# --------------------------------------------------------------------------- #

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "FlakeWin"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "run_flake.py")
    return f'"{sys.executable}" "{script}"'


def autostart_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _RUN_NAME)
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _RUN_NAME, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, _RUN_NAME)
                except OSError:
                    pass
    except OSError:
        pass


# --------------------------------------------------------------------------- #
#  Приложение
# --------------------------------------------------------------------------- #

class FlakeApp:
    def __init__(self) -> None:
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("Flake")
        self.app.setApplicationDisplayName("Flake")

        self.settings = Settings()
        self.engine = OverlayEngine(self.settings)
        self.engine.on_toast = self._toast
        self.sim = self.engine.sim
        self.sim.on_sign_request = self._ask_sign

        self.icon = make_snowflake_icon()
        self.app.setWindowIcon(self.icon)

        self.tray = QSystemTrayIcon(self.icon)
        self.tray.setToolTip("Flake — снег на рабочем столе")
        self.tray.setContextMenu(self._build_menu())
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    # ------------------------------------------------------------------ #
    def _toast(self, text: str) -> None:
        if self.tray.isVisible() and self.tray.supportsMessages():
            self.tray.showMessage("Flake", text, self.icon, 2200)

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_pause()

    # ------------------------------------------------------------------ #
    def _build_menu(self) -> QMenu:
        menu = QMenu()
        menu.aboutToShow.connect(self._refresh_menu)
        self.menu = menu
        self._refresh_menu()
        return menu

    def _refresh_menu(self) -> None:
        menu = self.menu
        menu.clear()
        sim = self.sim

        act = menu.addAction("Продолжить снег" if sim.paused else "Пауза")
        act.triggered.connect(self._toggle_pause)

        menu.addSeparator()

        intensity_menu = menu.addMenu("Интенсивность")
        group = QActionGroup(intensity_menu)
        group.setExclusive(True)
        for title, value in INTENSITY_PRESETS:
            action = intensity_menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(abs(self.settings["intensity"] - value) < 0.01)
            action.triggered.connect(lambda _c=False, v=value: self._set_intensity(v))
            group.addAction(action)

        act = menu.addAction("Мышь: вкл" if sim.mouse_enabled else "Мышь: выкл")
        act.triggered.connect(self._toggle_mouse)

        menu.addSeparator()

        act = menu.addAction("Растаять всё")
        act.triggered.connect(self._melt)

        act = menu.addAction("Снеговик (поставить)")
        act.triggered.connect(self._spawn_snowman)

        act = menu.addAction("Убрать снеговиков")
        act.triggered.connect(self._clear_snowmen)

        train_menu = menu.addMenu("Паровозик")
        act = train_menu.addAction("Пустить сейчас")
        act.triggered.connect(self._summon_train)
        act = train_menu.addAction("Катается сам")
        act.setCheckable(True)
        act.setChecked(bool(sim.train_runner.enabled))
        act.triggered.connect(self._toggle_train)
        train_menu.addSeparator()
        act = train_menu.addAction("Музыка под уборку")
        act.setCheckable(True)
        act.setChecked(bool(self.settings["music_enabled"]))
        act.triggered.connect(lambda checked: self._toggle_music(checked))
        volume_menu = train_menu.addMenu("Громкость музыки")
        for label, value in (("Тихо", 30), ("Средне", 60), ("Громко", 90)):
            item = volume_menu.addAction(label)
            item.setCheckable(True)
            item.setChecked(int(self.settings["music_volume"]) == value)
            item.triggered.connect(
                lambda _c=False, v=value: self._set_music_volume(v)
            )

        wallpaper_menu = menu.addMenu("Новогодние обои")
        for label, name in self._bundled_wallpapers():
            item = wallpaper_menu.addAction(label)
            item.triggered.connect(
                lambda _c=False, asset=name, title=label: self._apply_bundled(asset, title)
            )
        wallpaper_menu.addSeparator()
        act = wallpaper_menu.addAction("Ночная зима (рисованная)")
        act.triggered.connect(lambda: self._apply_wallpaper("night"))
        act = wallpaper_menu.addAction("Морозное утро (рисованное)")
        act.triggered.connect(lambda: self._apply_wallpaper("frost"))

        customs = self._custom_wallpapers()
        if customs:
            custom_menu = wallpaper_menu.addMenu(f"Мои обои ({len(customs)})")
            for path in customs[:24]:
                item = custom_menu.addAction(path.stem[:48])
                item.triggered.connect(
                    lambda _c=False, chosen=path: self._apply_custom(chosen)
                )

        wallpaper_menu.addSeparator()
        act = wallpaper_menu.addAction("Добавить из файла…")
        act.triggered.connect(self._import_wallpaper)
        act = wallpaper_menu.addAction("Открыть папку обоев")
        act.triggered.connect(self._open_wallpaper_folder)
        wallpaper_menu.addSeparator()
        act = wallpaper_menu.addAction("Вернуть прежние")
        act.triggered.connect(self._restore_wallpaper)

        menu.addSeparator()

        act = menu.addAction("Скрывать снег над развёрнутыми окнами")
        act.setCheckable(True)
        act.setChecked(bool(self.settings["hide_on_maximized"]))
        act.triggered.connect(self._toggle_hide_maximized)

        act = menu.addAction("Запускать с Windows")
        act.setCheckable(True)
        act.setChecked(autostart_enabled())
        act.triggered.connect(self._toggle_autostart)

        menu.addSeparator()

        act = menu.addAction("О программе")
        act.triggered.connect(self._about)

        act = menu.addAction("Выход")
        act.triggered.connect(self.quit)

    # ------------------------------------------------------------------ #
    def _toggle_pause(self) -> None:
        self.engine.set_paused(not self.sim.paused)

    def _set_intensity(self, value: float) -> None:
        self.engine.set_intensity(value)

    def _toggle_mouse(self) -> None:
        self.engine.set_mouse_enabled(not self.sim.mouse_enabled)

    def _melt(self) -> None:
        self.engine.melt()

    def _toggle_hide_maximized(self) -> None:
        self.engine.set_hide_maximized(not bool(self.settings["hide_on_maximized"]))

    def _toggle_autostart(self) -> None:
        set_autostart(not autostart_enabled())

    # ------------------------------------------------------------------ #
    def _spawn_snowman(self) -> None:
        """Поставить снеговика на видное место — на кромку самого широкого окна."""
        sim = self.sim
        ledges = [lg for lg in sim.snapshot.ledges if lg.can_accumulate]
        windows = [lg for lg in ledges if not lg.is_taskbar and lg.width >= 320]
        target = max(windows, key=lambda lg: lg.width) if windows else None
        if target is None and ledges:
            target = max(ledges, key=lambda lg: lg.width)

        if target is not None:
            x = target.x + target.width * random.uniform(0.34, 0.66)
            y = target.top - 30.0
        else:
            bounds = self.engine.world.bounds()
            x = bounds.center().x()
            y = bounds.center().y()

        man = sim.place_snowman(x, y)
        if man is None:
            from .sim import MAX_SNOWMEN

            self._toast(f"Уже {MAX_SNOWMEN} снеговика — больше не помещается")
            return
        state = "на окне" if man.resting else "падает на кромку"
        self._toast(f"Снеговик поставлен ({state}) — иногда кидает снежки")

    def _clear_snowmen(self) -> None:
        self.sim.clear_snowmen()
        self._toast("Снеговики убраны")

    def _summon_train(self) -> None:
        self.sim.train_runner.summon()
        self._toast("Паровозик выехал чистить снег")

    def _toggle_train(self) -> None:
        enabled = not self.sim.train_runner.enabled
        self.sim.train_runner.enabled = enabled
        self.settings["train_enabled"] = enabled
        if enabled:
            self.sim.train_runner.cooldown = min(self.sim.train_runner.cooldown, 8.0)

    def _toggle_music(self, checked: bool) -> None:
        self.engine.set_music_enabled(bool(checked))
        self._toast("Музыка под уборку включена" if checked
                    else "Музыка под уборку выключена")

    def _set_music_volume(self, value: int) -> None:
        self.engine.set_music_volume(value)
        self._toast(f"Громкость музыки: {value}%")

    def _apply_wallpaper(self, variant: str) -> None:
        from PySide6.QtGui import QGuiApplication

        from .wallpaper import apply_wallpaper

        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self._toast("Не удалось определить экран")
            return
        dpr = float(screen.devicePixelRatio() or 1.0)
        geometry = screen.geometry()
        path = apply_wallpaper(
            int(geometry.width() * dpr), int(geometry.height() * dpr),
            variant, self.settings,
        )
        if path:
            self._toast("Новогодние обои поставлены")
        else:
            self._toast("Не удалось поставить обои")

    def _restore_wallpaper(self) -> None:
        from .wallpaper import restore_wallpaper

        if restore_wallpaper(self.settings):
            self._toast("Прежние обои вернулись")
        else:
            self._toast("Прежние обои не сохранены")

    # ------------------------------------------------------------------ #
    def _bundled_wallpapers(self):
        try:
            from .wallpaper import bundled_wallpapers

            return bundled_wallpapers()
        except Exception:
            return []

    def _apply_bundled(self, name: str, label: str) -> None:
        from .wallpaper import apply_bundled

        if apply_bundled(name, self.settings):
            self._toast(f"Обои: {label}")
        else:
            self._toast("Не удалось поставить обои")

    def _custom_wallpapers(self):
        try:
            from .wallpaper import custom_wallpapers

            return custom_wallpapers()
        except Exception:
            return []

    def _apply_custom(self, path) -> None:
        from .wallpaper import apply_image

        if apply_image(path, self.settings):
            self._toast(f"Обои: {path.stem}")
        else:
            self._toast("Не удалось поставить обои")

    def _import_wallpaper(self) -> None:
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        from .wallpaper import import_wallpaper

        chosen, _ = QFileDialog.getOpenFileName(
            None,
            "Картинка для обоев",
            str(Path.home()),
            "Картинки (*.jpg *.jpeg *.png *.bmp *.webp)",
        )
        if not chosen:
            return
        target = import_wallpaper(chosen)
        if target is None:
            self._toast("Не удалось добавить картинку")
            return
        self._apply_custom(target)

    def _open_wallpaper_folder(self) -> None:
        from .wallpaper import CUSTOM_DIR

        CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(CUSTOM_DIR))
        except OSError:
            self._toast("Не удалось открыть папку")

    def _ask_sign(self, man: Snowman) -> None:
        text, ok = QInputDialog.getText(
            None, "Табличка снеговика",
            "Напиши текст на табличку:", text=man.sign_text,
        )
        if ok:
            man.sign_text = text.strip()

    def _about(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            None, "Flake для Windows",
            "Flake — снег на рабочем столе.\n\n"
            "• Снег идёт поверх окон и копится сугробами на их верхних кромках\n"
            "• Проведите мышью по сугробу — останется борозда\n"
            "• Зажмите кнопку мыши и покатайте по сугробу — слепится снежок\n"
            "• Отпустите с размахом — снежок полетит\n"
            "• Три снежка друг на друге → снеговик\n"
            "• Снеговика можно перетащить ЛКМ, он сам иногда кидает снежки\n"
            "• Правый клик по снеговику — табличка с надписью\n"
            "• Паровозик катается по панели задач и расчищает снег\n"
            "• «Новогодние обои» ставят зимнюю картинку на рабочий стол\n\n"
            "Вдохновлено Flake для macOS (github.com/ArturTonoyan/flake).",
        )

    # ------------------------------------------------------------------ #
    def run(self) -> int:
        self.engine.start()
        QTimer.singleShot(400, self._welcome)
        return self.app.exec()

    def _welcome(self) -> None:
        self._toast("Снег пошёл. Значок снежинки — в трее.")

    def quit(self) -> None:
        try:
            self.engine.stop()
        finally:
            self.tray.hide()
            self.app.quit()


def _acquire_single_instance():
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            return None
        return handle
    except Exception:
        return None


def main() -> int:
    mutex = _acquire_single_instance()
    if mutex is None and "--allow-multi" not in sys.argv:
        app = QApplication.instance() or QApplication(sys.argv)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(None, "Flake", "Flake уже запущен — ищите снежинку в трее.")
        return 0

    flake = FlakeApp()
    return flake.run()

"""Музыка паровозика: MCI (winmm), без внешних зависимостей.

Мелодия плавно появляется, когда поезд выезжает на уборку, и стихает,
когда он уезжает.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
from pathlib import Path

from .settings import APP_DIR

ASSETS_AUDIO = Path(__file__).resolve().parent / "assets" / "audio"
AUDIO_DIR = APP_DIR / "audio"
ALIAS = "flaketrain"

_winmm = ctypes.WinDLL("winmm")
_mci = _winmm.mciSendStringW
_mci.restype = wt.DWORD
_mci.argtypes = [wt.LPCWSTR, wt.LPWSTR, wt.UINT, wt.HWND]


def _send(command: str) -> int:
    try:
        return int(_mci(command, None, 0, None))
    except Exception:
        return 1


def _query(command: str) -> str:
    buffer = ctypes.create_unicode_buffer(128)
    try:
        code = _mci(command, buffer, 128, None)
    except Exception:
        return ""
    return buffer.value if code == 0 else ""


def music_file() -> Path | None:
    """Постоянная копия мелодии (временную папку сборки Windows может удалить)."""
    bundled = ASSETS_AUDIO / "train.mp3"
    if not bundled.is_file():
        return None
    try:
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        target = AUDIO_DIR / "train.mp3"
        if (not target.exists()
                or target.stat().st_size != bundled.stat().st_size):
            import shutil

            shutil.copy2(bundled, target)
        return target
    except OSError:
        return bundled


class TrainMusic:
    """Проигрывание с плавным входом и затуханием."""

    FADE_IN = 1.1
    FADE_OUT = 1.5

    def __init__(self, volume: int = 60, enabled: bool = True) -> None:
        self.path = music_file()
        self.enabled = bool(enabled) and self.path is not None
        self.volume = max(0, min(100, int(volume)))
        self._opened = False
        self._want = False
        self._preview = 0.0
        self._level = 0.0
        self._check_cd = 0.0

    # ------------------------------------------------------------------ #
    def _open(self) -> bool:
        if self._opened:
            return True
        if not self.enabled or self.path is None:
            return False
        if _send(f'open "{self.path}" type mpegvideo alias {ALIAS}') != 0:
            self.enabled = False
            return False
        _send(f"set {ALIAS} time format milliseconds")
        self._opened = True
        self._apply(0.0)
        return True

    def _apply(self, level: float) -> None:
        value = int(round(max(0.0, min(1.0, level)) * self.volume * 10))
        _send(f"setaudio {ALIAS} volume to {value}")

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Поезд выехал — мелодия появляется."""
        if not self.enabled or self._want:
            return
        if not self._open():
            return
        self._want = True
        _send(f"seek {ALIAS} to start")
        _send(f"play {ALIAS}")

    def stop(self) -> None:
        """Поезд уехал — мелодия стихает (само затухание идёт в update)."""
        self._want = False

    def preview(self, seconds: float = 3.0) -> None:
        """Короткий фрагмент — например, когда музыку только включили."""
        self._preview = max(self._preview, seconds)
        self.start()

    def previewing(self) -> bool:
        return self._preview > 0.0

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled) and self.path is not None
        if not self.enabled:
            self._want = False
            self._stop_device()

    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, int(volume)))
        self._apply(self._level)

    # ------------------------------------------------------------------ #
    def update(self, dt: float) -> None:
        if self._preview > 0.0:
            self._preview = max(0.0, self._preview - dt)
            if self._preview <= 0.0:
                self._want = False

        if not self._opened:
            return

        target = 1.0 if self._want else 0.0
        if self._level < target:
            self._level = min(target, self._level + dt / self.FADE_IN)
        elif self._level > target:
            self._level = max(target, self._level - dt / self.FADE_OUT)
        self._apply(self._level)

        if self._want:
            # Зацикливаем: трек короче, чем иной рейс.
            self._check_cd -= dt
            if self._check_cd <= 0.0:
                self._check_cd = 0.4
                if _query(f"status {ALIAS} mode") != "playing":
                    _send(f"seek {ALIAS} to start")
                    _send(f"play {ALIAS}")
        elif self._level <= 0.001 and _query(f"status {ALIAS} mode") != "stopped":
            self._stop_device()

    def _stop_device(self) -> None:
        if not self._opened:
            return
        _send(f"stop {ALIAS}")
        _send(f"seek {ALIAS} to start")
        self._level = 0.0
        self._apply(0.0)

    def close(self) -> None:
        if not self._opened:
            return
        self._want = False
        _send(f"stop {ALIAS}")
        _send(f"close {ALIAS}")
        self._opened = False
        self._level = 0.0

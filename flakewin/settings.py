"""Настройки Flake для Windows: %APPDATA%\\FlakeWin\\settings.json."""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "FlakeWin"
SETTINGS_PATH = APP_DIR / "settings.json"

DEFAULTS = {
    "intensity": 0.7,
    "mouse_enabled": True,
    "paused": False,
    "hide_on_maximized": False,
    "train_enabled": True,
    "snowman_scale": 1.55,
    "wallpaper_backup": "",
    "autostart": False,
    "lan_enabled": False,
    "lan_name": "",
    "fps_limit": 30,
}


class Settings:
    def __init__(self) -> None:
        self.data = dict(DEFAULTS)
        self.load()

    # ------------------------------------------------------------------ #
    def load(self) -> None:
        try:
            if SETTINGS_PATH.exists():
                raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for key, value in raw.items():
                        if key in DEFAULTS:
                            self.data[key] = value
        except Exception:
            pass
        self.data["intensity"] = float(
            min(1.4, max(0.25, float(self.data.get("intensity", 0.7))))
        )
        if not self.data.get("lan_name"):
            self.data["lan_name"] = os.environ.get("COMPUTERNAME", "Flake-PC")

    def save(self) -> None:
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def __getitem__(self, key: str):
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key: str, value) -> None:
        self.data[key] = value
        self.save()

    def toggle(self, key: str) -> bool:
        value = not bool(self[key])
        self[key] = value
        return value

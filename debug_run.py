"""Диагностический прогон движка (для отладки оверлея)."""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from flakewin import winapi
from flakewin.overlay import OverlayEngine, SnowOverlay
from flakewin.settings import Settings

paints = {"n": 0}
_orig = SnowOverlay.paintEvent


def _patched(self, event):
    paints["n"] += 1
    _orig(self, event)


SnowOverlay.paintEvent = _patched


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    settings = Settings()
    settings.data["paused"] = False
    engine = OverlayEngine(settings)
    engine.start()

    def report() -> None:
        print("=== OVERLAY STATE ===")
        print("screens:", [(s.index, s.logical, s.dpr, s.physical)
                           for s in engine.world.screens])
        print("overlays:", len(engine.overlays), "paints:", paints["n"])
        for o in engine.overlays:
            hwnd = int(o.winId())
            print(f"  overlay[{o.screen.index}] geom={o.geometry()} visible={o.isVisible()}"
                  f" exstyle={hex(winapi.ex_style(hwnd))} hwnd={hwnd}")
        snap = engine.sim.snapshot
        print("ledges:", len(snap.ledges))
        for lg in snap.ledges:
            print(f"  {lg.id} x={lg.x:.0f} top={lg.top:.0f} w={lg.width:.0f}"
                  f" z={lg.z} acc={lg.can_accumulate} bar={lg.is_taskbar}")
        print("occluders:", len(snap.occluders))
        print("blocked:", [(round(b.x()), round(b.y()), round(b.width()), round(b.height()))
                           for b in snap.blocked])
        print("surfaces:", len(engine.sim.surfaces),
              "flakes:", engine.sim.field.count,
              "balls:", len(engine.sim.balls),
              "snowmen:", len(engine.sim.snowmen))
        print("mouse:", round(engine.sim.mouse_x), round(engine.sim.mouse_y))

    QTimer.singleShot(2600, report)
    QTimer.singleShot(3600, app.quit)
    app.exec()
    engine.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

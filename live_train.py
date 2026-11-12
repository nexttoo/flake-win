"""Живой прогон паровозика: накопление снега на панели и расчистка."""
from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from flakewin.overlay import OverlayEngine
from flakewin.settings import Settings


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    settings = Settings()
    settings.data["intensity"] = 1.0
    engine = OverlayEngine(settings)
    engine.start()
    started = time.perf_counter()

    def report() -> None:
        sim = engine.sim
        bar = next((lg for lg in sim.snapshot.ledges if lg.is_taskbar), None)
        surface = sim.surfaces.get(bar.id) if bar is not None else None
        level = float(surface.h.mean()) if surface is not None and surface.h.size else 0.0
        train = sim.train_runner.train
        where = f"x={train.x:.0f}" if train is not None else "-"
        print(f"{time.perf_counter() - started:5.1f}s level={level:5.2f}"
              f" train={where:>9} flakes={sim.field.count}", flush=True)

    timer = QTimer()
    timer.timeout.connect(report)
    timer.start(5000)
    QTimer.singleShot(115_000, app.quit)
    app.exec()
    engine.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

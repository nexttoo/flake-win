"""Живой прогон новых функций: снеговик на окне, паровозик, обои."""
from __future__ import annotations

import sys

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

    def act() -> None:
        sim = engine.sim
        ledges = [lg for lg in sim.snapshot.ledges if lg.can_accumulate]
        windows = [lg for lg in ledges if not lg.is_taskbar and lg.width >= 320]
        target = max(windows, key=lambda lg: lg.width) if windows else None
        if target is None:
            target = next((lg for lg in ledges if lg.is_taskbar), None)
        if target is not None:
            man = sim.place_snowman(target.x + target.width * 0.5, target.top - 30)
            print(f"placed on {man.resting} x={man.x:.0f} y={man.y:.0f}", flush=True)
        else:
            print("no ledge", flush=True)
        sim.train_runner.summon()
        print(f"ledges={[(l.id, round(l.top), l.can_accumulate) for l in ledges]}",
              flush=True)

    def report() -> None:
        sim = engine.sim
        for man in sim.snowmen:
            print(f"snowman x={man.x:.0f} y={man.y:.0f} resting={man.resting}"
                  f" held={man.held} perform={man.perform_t:.2f}", flush=True)
        print(f"balls={len(sim.balls)} train={sim.train_runner.train is not None}"
              f" flakes={sim.field.count}", flush=True)

    QTimer.singleShot(4000, act)
    QTimer.singleShot(12000, report)
    QTimer.singleShot(22000, report)
    QTimer.singleShot(26000, app.quit)
    app.exec()
    engine.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

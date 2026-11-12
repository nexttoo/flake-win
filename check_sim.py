"""Проверка физики без экрана: накопление сугробов, снежки, снеговик."""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from flakewin.settings import Settings
from flakewin.sim import MAX_SNOWMEN, Simulator, Snowball, Snowman
from flakewin.tracker import Ledge, Occluder, Snapshot, WindowTracker
from flakewin.world import Screen, World


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    settings = Settings()
    settings.data["intensity"] = 1.0

    world = World()
    world.screens = [Screen(0, "test", QRect(0, 0, 1920, 1080), 1.0, QRect(0, 0, 1920, 1080))]
    tracker = WindowTracker(world)
    sim = Simulator(world, tracker, settings)
    sim.intensity = 1.0

    ledges = [
        Ledge("w0", 120, 200, 900, 0, can_accumulate=True),
        Ledge("w1", 1100, 420, 700, 1, can_accumulate=True),
        Ledge("taskbar", 0, 1032, 1920, -1000, is_taskbar=True),
    ]
    occluders = [
        Occluder("w0", 120, 200, 1020, 700, 0),
        Occluder("w1", 1100, 420, 1800, 900, 1),
        Occluder("taskbar", 0, 1032, 1920, 1080, -1000, is_taskbar=True),
    ]
    sim.snapshot = Snapshot(ledges=ledges, occluders=occluders, blocked=[],
                            foreground=0, signature=())
    sim._sync_surfaces()

    dt = 1.0 / 30.0
    for step in range(30 * 90):
        sim.snapshot = Snapshot(ledges=ledges, occluders=occluders, blocked=[],
                                foreground=0, signature=())
        sim._update_wind(dt)
        sim._spawn(dt)
        sim._integrate(dt)
        if step % 300 == 0:
            peaks = {lid: round(s.peak, 1) for lid, s in sim.surfaces.items()}
            print(f"t={step/30:5.1f}s flakes={sim.field.count:5d} peaks={peaks}")

    print("--- итог через 90 с ---")
    for lid, surface in sim.surfaces.items():
        nonzero = int((surface.h > 0.2).sum())
        print(f"  {lid}: peak={surface.peak:.1f} cells_with_snow={nonzero}/{surface.h.size}")

    # Снежок падает на сугроб и ложится на кромку.
    sim.balls.append(Snowball(600, 100, 0, 250, 18.0))
    for _ in range(60):
        sim._update_balls(dt)
    b = sim.balls[0]
    print(f"ball: x={b.x:.0f} y={b.y:.0f} resting={b.resting} r={b.radius:.1f}")

    # Укладка трёх снежков -> снеговик (роняем их друг на друга).
    sim.balls.clear()
    sim.snowmen.clear()
    for i in range(3):
        ball = Snowball(500.0 + i * 0.5, 120.0, 0, 0, 20.0)
        sim.balls.append(ball)
        for _ in range(120):
            sim._update_balls(dt)
            if sim.balls and sim.balls[-1].resting is not None:
                break
        print(f"  drop {i+1}: balls={len(sim.balls)} snowmen={len(sim.snowmen)}"
              f" resting={sim.balls[-1].resting if sim.balls else '-'}")
    print(f"after stack: balls={len(sim.balls)} snowmen={len(sim.snowmen)}")
    if sim.snowmen:
        m = sim.snowmen[0]
        print(f"  snowman base_r={m.base_r:.1f} mid_r={m.mid_r:.1f} head_r={m.head_r:.1f}"
              f" top_y={m.top_y:.0f}")

    # Мышь: разгребание сугроба.
    surface = sim.surfaces["w0"]
    before = surface.peak
    sim.mouse_x, sim.mouse_y = 500, 200 - before - 4
    sim.mouse_vx, sim.mouse_vy = 60, 18
    sim.mouse_down = False
    for _ in range(20):
        sim._plow_or_scoop(dt)
    print(f"plow: peak {before:.1f} -> {surface.peak:.1f}")

    # --- снеговик: постановка, устойчивость, собственные броски ---
    print("--- снеговик ---")
    sim.snowmen.clear()
    sim.balls.clear()
    sim.mouse_x, sim.mouse_y = 20.0, 20.0  # мышь далеко, наведения нет
    man = sim.place_snowman(600.0, 150.0)
    print(f"поставлен: resting={man.resting} x={man.x:.0f} y={man.y:.0f}"
          f" base_r={man.base_r:.1f}")
    throws = 0
    for _ in range(30 * 40):
        sim.snapshot = Snapshot(ledges=ledges, occluders=occluders, blocked=[],
                                foreground=0, signature=())
        before_balls = len(sim.balls)
        sim._update_snowmen(dt)
        sim._update_balls(dt)
        if len(sim.balls) > before_balls:
            throws += 1
    alive = man in sim.snowmen
    print(f"через 40 с: на месте={alive} resting={man.resting}"
          f" бросков={throws} снежков={len(sim.balls)}")

    # --- снеговики не должны размножаться сами ---
    print("--- снеговик-ферма ---")
    sim.snowmen.clear()
    sim.balls.clear()
    sim.mouse_x, sim.mouse_y = 20.0, 20.0
    placed = 0
    for i in range(6):
        if sim.place_snowman(300.0 + i * 120.0, 150.0) is not None:
            placed += 1
    print(f"поставлено вручную: {placed} (лимит {MAX_SNOWMEN})")
    for _ in range(30 * 60):
        sim.snapshot = Snapshot(ledges=ledges, occluders=occluders, blocked=[],
                                foreground=0, signature=())
        sim._update_snowmen(dt)
        sim._update_balls(dt)
    print(f"через 60 с: снеговиков={len(sim.snowmen)}"
          f" снежков={len(sim.balls)}")

    # --- паровозик ---
    print("--- паровозик ---")
    sim.train_runner.enabled = True
    sim.train_runner.cooldown = 0.0
    sim.train_runner.update(0.0, sim)
    train = sim.train_runner.train
    print("поезд:", "-" if train is None else
          f"x={train.x:.0f} dir={train.direction}")
    bar_surface = sim.surfaces["taskbar"]
    before_sum = float(bar_surface.h.sum())
    before_peak = bar_surface.peak
    moved = 0.0
    if train is not None:
        start_x = train.x
        for _ in range(30 * 14):
            sim.train_runner.update(dt, sim)
            if sim.train_runner.train is not None:
                moved = abs(sim.train_runner.train.x - start_x)
    after_sum = float(bar_surface.h.sum())
    print(f"панель задач: суммарный снег {before_sum:.0f} -> {after_sum:.0f}"
          f" (peak {before_peak:.1f} -> {bar_surface.peak:.1f}),"
          f" проехал {moved:.0f} px, дым={len(train.puffs) if train else 0}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

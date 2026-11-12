"""Оффлайн-рендер кадра Flake — проверка визуала без рабочего стола.

Запуск:  python run_flake.py --selftest out.png
"""
from __future__ import annotations

import math
import random
import sys

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QLinearGradient,
                           QPainter, QPen)
from PySide6.QtWidgets import QApplication

from .render import Renderer
from .settings import Settings
from .sim import Simulator, Snowball, Snowman
from .tracker import Ledge, Occluder, Snapshot, WindowTracker
from .world import Screen, World

WINDOWS = (
    ("Документ — Word", 96, 176, 660, 396),
    ("Проводник", 812, 96, 620, 440),
    ("Терминал", 300, 566, 780, 246),
)


def _scene(width: int, height: int):
    ledges: list[Ledge] = []
    occluders: list[Occluder] = []
    for index, (_name, x, y, w, h) in enumerate(WINDOWS):
        lid = f"w{index}"
        ledges.append(Ledge(lid, x, y, w, index, can_accumulate=True))
        occluders.append(Occluder(lid, x, y, x + w, y + h, index))
    ledges.append(Ledge("taskbar", 0, height - 46, width, -1000, is_taskbar=True))
    occluders.append(Occluder("taskbar", 0, height - 46, width, height, -1000,
                              is_taskbar=True))
    return ledges, occluders


def _paint_desktop(p: QPainter, width: int, height: int) -> None:
    sky = QLinearGradient(0, 0, width * 0.35, height)
    sky.setColorAt(0.0, QColor(24, 38, 66))
    sky.setColorAt(0.45, QColor(38, 62, 98))
    sky.setColorAt(1.0, QColor(16, 26, 44))
    p.fillRect(QRect(0, 0, width, height), QBrush(sky))

    glow = QLinearGradient(0, height * 0.1, width, height * 0.9)
    glow.setColorAt(0.0, QColor(120, 170, 220, 26))
    glow.setColorAt(0.6, QColor(80, 130, 190, 10))
    glow.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.fillRect(QRect(0, 0, width, height), QBrush(glow))

    for _name, x, y, w, h in WINDOWS:
        body = QRectF(x, y, w, h)
        card = QLinearGradient(x, y, x, y + h)
        card.setColorAt(0.0, QColor(248, 250, 253))
        card.setColorAt(1.0, QColor(232, 238, 246))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(card))
        p.drawRoundedRect(body, 11, 11)

        bar = QRectF(x, y, w, 34)
        bar_grad = QLinearGradient(x, y, x, y + 34)
        bar_grad.setColorAt(0.0, QColor(223, 231, 241))
        bar_grad.setColorAt(1.0, QColor(205, 216, 230))
        p.setBrush(QBrush(bar_grad))
        p.drawRoundedRect(bar, 11, 11)
        p.drawRect(QRectF(x, y + 18, w, 16))

        p.setPen(QPen(QColor(120, 132, 150)))
        font = QFont("Segoe UI", 9)
        p.setFont(font)
        p.drawText(QRectF(x + 14, y + 6, w - 60, 22),
                   int(Qt.AlignmentFlag.AlignVCenter), _name)

        p.setPen(QPen(QColor(196, 208, 222)))
        p.drawLine(QPointF(x + 1, y + 34.5), QPointF(x + w - 1, y + 34.5))

        ink = QColor(168, 180, 196)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(ink))
        ty = y + 58
        widths = (0.72, 0.86, 0.55, 0.92, 0.64, 0.80, 0.45)
        i = 0
        while ty < y + h - 24:
            p.drawRoundedRect(QRectF(x + 18, ty, (w - 36) * widths[i % len(widths)], 7), 3, 3)
            ty += 17
            i += 1

    taskbar = QRectF(0, height - 46, width, 46)
    bar = QLinearGradient(0, height - 46, 0, height)
    bar.setColorAt(0.0, QColor(30, 40, 56, 235))
    bar.setColorAt(1.0, QColor(20, 28, 41, 245))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(bar))
    p.drawRect(taskbar)
    p.setBrush(QBrush(QColor(150, 200, 250, 200)))
    for i in range(6):
        p.drawRoundedRect(QRectF(28 + i * 44, height - 34, 26, 26), 6, 6)


def run_selftest(out_path: str, width: int = 1600, height: int = 900) -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    settings = Settings()
    world = World()
    world.screens = [Screen(0, "selftest", QRect(0, 0, width, height), 1.0,
                            QRect(0, 0, width, height))]
    tracker = WindowTracker(world)
    sim = Simulator(world, tracker, settings)
    sim.intensity = 1.15

    ledges, occluders = _scene(width, height)
    sim.snapshot = Snapshot(ledges=ledges, occluders=occluders, blocked=[],
                            foreground=0, signature=())
    sim._sync_surfaces()

    # Наметаем сугробы: несколько «метелей» с неровным профилем.
    random.seed(7)
    for lid, surface in sim.surfaces.items():
        n = surface.h.size
        xs = [i * surface.cell for i in range(n)]
        base = [max(0.35, 0.85 + 0.55 * math.sin(i * 0.045) + random.uniform(-0.25, 0.35))
                for i in range(n)]
        rounds = 4 if surface.is_taskbar else 9
        for _ in range(rounds):
            surface.deposit_many(xs, [b * random.uniform(0.85, 1.15) for b in base])

    # Снежинки в воздухе (только над свободным столом — как в реальном кадре).
    xs, ys = [], []
    while len(xs) < 760:
        px = random.uniform(0, width)
        py = random.uniform(0, height)
        inside = any(x <= px <= x + w and y <= py <= y + h
                     for _n, x, y, w, h in WINDOWS)
        if inside or py > height - 50:
            continue
        xs.append(px)
        ys.append(py)
    sim.field.spawn(xs, ys, sim.intensity, 0.0)
    for _ in range(2):
        sim._integrate(1.0 / 60.0)

    # Снеговик на среднем окне и пара снежков.
    name, x, y, w, h = WINDOWS[1]
    surface = sim.surfaces.get("w1")
    pile = surface.height_at(w * 0.32) if surface else 0.0
    man = Snowman(x + w * 0.32, y - pile - 20, 46.0, 24.0, 13.0)
    man.resting = "w1"
    man.sign_text = "Привет!"
    sim.snowmen.append(man)

    name2, x2, y2, w2, h2 = WINDOWS[0]
    surface2 = sim.surfaces.get("w0")
    pile2 = surface2.height_at(w2 * 0.68) if surface2 else 0.0
    sim.balls.append(Snowball(x2 + w2 * 0.68, y2 - pile2 - 15, 0, 0, 34.0))
    surface3 = sim.surfaces.get("taskbar")
    sim.balls.append(Snowball(width * 0.62, height - 46 - 12, 0, 0, 22.0))

    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.black)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    _paint_desktop(painter, width, height)

    renderer = Renderer()
    renderer.draw(painter, sim, 1.0, QRectF(0, 0, width, height))
    painter.end()

    ok = image.save(out_path, "PNG")
    print(f"selftest: {out_path} -> {ok}, flakes={sim.field.count}, "
          f"surfaces={len(sim.surfaces)}")
    return 0 if ok else 1

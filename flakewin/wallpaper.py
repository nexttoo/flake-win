"""Новогодние обои: сказочная зимняя сцена, нарисованная кодом.

Ничего не скачивается: сцена рисуется под разрешение экрана, поэтому
в интернете приложение не нуждается.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPolygonF, QRadialGradient)

from . import winapi
from .settings import APP_DIR

WALLPAPER_DIR = APP_DIR / "wallpaper"
CUSTOM_DIR = WALLPAPER_DIR / "custom"
SUPPORTED = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

# Готовые обои, которые поставляются вместе с приложением.
ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "wallpapers"
BUNDLED = (
    ("Зимняя ночь", "winter-night.jpg"),
    ("Зимнее утро", "winter-morning.jpg"),
)

PALETTES = {
    "night": {
        "sky": [(0.00, "#040a16"), (0.26, "#081a30"), (0.50, "#102a45"),
                (0.68, "#1d4260"), (0.84, "#3f6d8c")],
        "horizon_glow": (238, 172, 112, 118),
        "stars": 230,
        "far_trees": "#1d3a58",
        "mid_trees": "#132a40",
        "near_trees": "#080f1a",
        "snow": "#f4f8ff",
        "snow_shade": "#b9cfe8",
        "wood": "#5c3a22",
        "wood_dark": "#38200f",
        "roof": "#33241a",
        "warm": "#ffc776",
        "warm_strong": "#ffb457",
        "garland": True,
        "fog": (150, 186, 220, 46),
        "vignette": 175,
        "grain": 5200,
    },
    "frost": {
        "sky": [(0.00, "#4d80ae"), (0.26, "#7ba6c9"), (0.52, "#aecde4"),
                (0.72, "#d9e7f2"), (0.86, "#f3e2d5")],
        "horizon_glow": (255, 205, 160, 130),
        "stars": 0,
        "far_trees": "#9db8ce",
        "mid_trees": "#7796ae",
        "near_trees": "#3f586d",
        "snow": "#ffffff",
        "snow_shade": "#cfe1f0",
        "wood": "#7c4c30",
        "wood_dark": "#4e2c19",
        "roof": "#553624",
        "warm": "#ffd79a",
        "warm_strong": "#ffc470",
        "garland": False,
        "fog": (255, 255, 255, 60),
        "vignette": 80,
        "grain": 3000,
    },
}


# --------------------------------------------------------------------------- #
#  Мягкий свет
# --------------------------------------------------------------------------- #

def _glow(p: QPainter, x: float, y: float, radius: float,
          color: tuple[int, int, int], alpha: int) -> None:
    if radius <= 0.6 or alpha <= 0:
        return
    grad = QRadialGradient(QPointF(x, y), radius)
    grad.setColorAt(0.0, QColor(color[0], color[1], color[2], alpha))
    grad.setColorAt(0.38, QColor(color[0], color[1], color[2], int(alpha * 0.44)))
    grad.setColorAt(0.72, QColor(color[0], color[1], color[2], int(alpha * 0.12)))
    grad.setColorAt(1.0, QColor(color[0], color[1], color[2], 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawEllipse(QPointF(x, y), radius, radius)


def _glow_ellipse(p: QPainter, x: float, y: float, rx: float, ry: float,
                  color: tuple[int, int, int], alpha: int) -> None:
    if rx <= 0.6 or alpha <= 0:
        return
    p.save()
    p.translate(x, y)
    p.scale(rx / ry if ry else 1.0, 1.0)
    grad = QRadialGradient(QPointF(0, 0), ry)
    grad.setColorAt(0.0, QColor(color[0], color[1], color[2], alpha))
    grad.setColorAt(0.45, QColor(color[0], color[1], color[2], int(alpha * 0.38)))
    grad.setColorAt(1.0, QColor(color[0], color[1], color[2], 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawEllipse(QPointF(0, 0), ry, ry)
    p.restore()


# --------------------------------------------------------------------------- #
#  Ёлки
# --------------------------------------------------------------------------- #

def _fir(p: QPainter, x: float, base_y: float, height: float,
         color: str, snow: str, snow_amount: float,
         rnd: random.Random, tiers: int = 5, rim: str | None = None) -> None:
    """Ёлка: вогнутые ярусы-ветви + мелкий снег по кромкам ветвей."""
    p.setPen(Qt.PenStyle.NoPen)
    trunk = max(1.6, height * 0.020)
    p.setBrush(QBrush(QColor(color).darker(150)))
    p.drawRect(QRectF(x - trunk * 0.5, base_y - height * 0.09,
                      trunk, height * 0.11))

    base = QColor(color)
    apex = base_y - height
    for i in range(tiers):
        top = apex + height * (0.02 + i * (0.74 / tiers))
        bottom = min(apex + height * (0.34 + i * (0.74 / tiers)), base_y)
        if bottom - top < 3:
            continue
        half = height * (0.055 + i * 0.048)

        path = QPainterPath()
        path.moveTo(x, top)
        path.quadTo(x - half * 0.72, bottom - (bottom - top) * 0.30, x - half, bottom)
        path.quadTo(x - half * 0.35, bottom - (bottom - top) * 0.06, x,
                    bottom - (bottom - top) * 0.10)
        path.quadTo(x + half * 0.35, bottom - (bottom - top) * 0.06, x + half, bottom)
        path.quadTo(x + half * 0.72, bottom - (bottom - top) * 0.30, x, top)
        path.closeSubpath()

        shade = base.lighter(100 + (tiers - i) * 5)
        p.setBrush(QBrush(shade))
        p.drawPath(path)

        # Тень под ярусом — объём без «коричневой заливки».
        p.setBrush(QBrush(QColor(0, 0, 0, 46)))
        p.drawEllipse(QPointF(x, bottom), half * 0.92, (bottom - top) * 0.055)

        # Тонкая подсветка со стороны дома.
        if rim is not None:
            edge = QColor(rim)
            edge.setAlphaF(0.30)
            pen = QPen(edge)
            pen.setWidthF(max(0.7, height * 0.0035))
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            side = -1.0 if x < width_ref[0] else 1.0
            p.drawLine(QPointF(x + side * half * 0.98, bottom - 1),
                       QPointF(x + side * half * 0.42, bottom - (bottom - top) * 0.55))
            p.setPen(Qt.PenStyle.NoPen)

        # Снег лежит по кромке ветвей: линия + мелкие комки.
        if snow_amount > 0.02:
            notch = (bottom - top) * 0.10
            edge = QPolygonF([
                QPointF(x - half, bottom),
                QPointF(x - half * 0.35, bottom - notch * 0.6),
                QPointF(x, bottom - notch),
                QPointF(x + half * 0.35, bottom - notch * 0.6),
                QPointF(x + half, bottom),
            ])
            cap = QColor(snow)
            cap.setAlphaF(min(1.0, 0.42 + snow_amount * 0.5))
            pen = QPen(cap)
            pen.setWidthF(max(1.0, height * 0.0055))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolyline(edge)
            p.setPen(Qt.PenStyle.NoPen)

            flakes = max(5, int(half / max(2.0, height * 0.012)))
            p.setBrush(QBrush(cap))
            for k in range(flakes):
                t = (k + 0.5) / flakes + rnd.uniform(-0.25, 0.25) / flakes
                bx = x + (t * 2.0 - 1.0) * half * 0.95
                dip = 1.0 - abs(t * 2.0 - 1.0)
                by = bottom - notch * dip - height * rnd.uniform(0.0, 0.004)
                radius = height * rnd.uniform(0.0022, 0.0044) * (0.8 + snow_amount * 0.5)
                p.drawEllipse(QPointF(bx, by), radius * 1.7, radius)

            p.drawEllipse(QPointF(x, top + (bottom - top) * 0.02),
                          half * 0.07, (bottom - top) * 0.02)


# Опорная точка для выбора освещённой стороны (ставится перед отрисовкой сцены).
width_ref = [960.0]


def _forest(p: QPainter, width: float, height: float, base_y: float,
            count: int, color: str, snow: str, h_min: float, h_max: float,
            snow_amount: float, rnd: random.Random,
            jitter: float = 0.0, rim: str | None = None) -> None:
    for _ in range(count):
        x = rnd.uniform(-0.04, 1.04) * width
        h = rnd.uniform(h_min, h_max) * height
        y = base_y + rnd.uniform(-jitter, jitter) * height
        _fir(p, x, y, h, color, snow, snow_amount, rnd, tiers=4, rim=rim)


def _icicles(p: QPainter, x0: float, x1: float, y: float,
             count: int, rnd: random.Random) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(count):
        t = (i + rnd.uniform(0.1, 0.9)) / max(1, count)
        x = x0 + (x1 - x0) * t
        length = rnd.uniform(5.0, 16.0)
        width = rnd.uniform(1.8, 3.6)
        grad = QLinearGradient(x, y, x, y + length)
        grad.setColorAt(0.0, QColor(236, 246, 255, 230))
        grad.setColorAt(1.0, QColor(196, 220, 245, 60))
        p.setBrush(QBrush(grad))
        p.drawPolygon(QPolygonF([
            QPointF(x - width * 0.5, y),
            QPointF(x + width * 0.5, y),
            QPointF(x + width * 0.08, y + length),
        ]))


def _garland(p: QPainter, points: list[QPointF], warm: str,
             step: float, scale: float) -> None:
    if len(points) < 2:
        return
    path = QPainterPath(points[0])
    for point in points[1:]:
        path.lineTo(point)

    pen = QPen(QColor(42, 30, 20, 200))
    pen.setWidthF(max(0.7, 1.0 * scale))
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)

    lengths: list[float] = []
    total = 0.0
    for i in range(1, len(points)):
        seg = math.hypot(points[i].x() - points[i - 1].x(),
                         points[i].y() - points[i - 1].y())
        lengths.append(seg)
        total += seg
    if total <= 1:
        return

    p.setPen(Qt.PenStyle.NoPen)
    bulb = QColor(warm)
    travelled = 0.0
    next_at = step * 0.5
    for i in range(1, len(points)):
        seg = lengths[i - 1]
        while next_at <= travelled + seg:
            local = (next_at - travelled) / max(0.001, seg)
            x = points[i - 1].x() + (points[i].x() - points[i - 1].x()) * local
            y = points[i - 1].y() + (points[i].y() - points[i - 1].y()) * local
            _glow(p, x, y, 4.6 * scale, (255, 198, 126), 110)
            p.setBrush(QBrush(QColor(255, 240, 200)))
            p.drawEllipse(QPointF(x, y), 1.5 * scale, 1.5 * scale)
            p.setBrush(QBrush(bulb))
            p.drawEllipse(QPointF(x, y), 0.9 * scale, 0.9 * scale)
            next_at += step
        travelled += seg


# --------------------------------------------------------------------------- #
#  Изба
# --------------------------------------------------------------------------- #

def _cabin(p: QPainter, cx: float, base_y: float, s: float, pal: dict,
           rnd: random.Random) -> None:
    warm = QColor(pal["warm"])
    wood = QColor(pal["wood"])
    wood_dark = QColor(pal["wood_dark"])
    snow = QColor(pal["snow"])

    wall_w, wall_h = 252 * s, 116 * s
    left = cx - wall_w * 0.5
    top = base_y - wall_h

    # Свет из окон на снегу — до стен, чтобы стены его перекрывали.
    _glow_ellipse(p, cx - 56 * s, base_y + 26 * s, 120 * s, 46 * s,
                  (255, 188, 118), 70)
    _glow_ellipse(p, cx + 34 * s, base_y + 24 * s, 110 * s, 42 * s,
                  (255, 188, 118), 62)
    _glow(p, cx, base_y, 210 * s, (255, 176, 104), 26)

    # Стены.
    wall_grad = QLinearGradient(left, 0, left + wall_w, 0)
    wall_grad.setColorAt(0.0, wood.darker(140))
    wall_grad.setColorAt(0.5, wood)
    wall_grad.setColorAt(1.0, wood.darker(122))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(wall_grad))
    p.drawRect(QRectF(left, top, wall_w, wall_h))

    # Венцы.
    pen = QPen(QColor(wood_dark.red(), wood_dark.green(), wood_dark.blue(), 170))
    pen.setWidthF(max(0.6, 0.9 * s))
    p.setPen(pen)
    for i in range(1, 8):
        y = top + wall_h * i / 8.0
        p.drawLine(QPointF(left, y), QPointF(left + wall_w, y))
    p.setPen(Qt.PenStyle.NoPen)

    # Фронтон.
    gable = QPolygonF([
        QPointF(left - 3 * s, top + 2 * s),
        QPointF(cx, top - 112 * s),
        QPointF(left + wall_w + 3 * s, top + 2 * s),
    ])
    gable_grad = QLinearGradient(cx, top - 112 * s, cx, top)
    gable_grad.setColorAt(0.0, wood.lighter(112))
    gable_grad.setColorAt(1.0, wood.darker(112))
    p.setBrush(QBrush(gable_grad))
    p.drawPolygon(gable)

    # Крыша.
    eave_y = top - 2 * s
    eave_l = QPointF(left - 32 * s, eave_y)
    eave_r = QPointF(left + wall_w + 32 * s, eave_y)
    ridge = QPointF(cx, top - 126 * s)
    p.setBrush(QBrush(QColor(pal["roof"])))
    p.drawPolygon(QPolygonF([eave_l, ridge, eave_r]))

    # Снег на скатах: изогнутая полоса, лежит на крыше.
    snow_path = QPainterPath()
    snow_path.moveTo(eave_l.x() - 3 * s, eave_l.y() - 4 * s)
    snow_path.quadTo((eave_l.x() + ridge.x()) * 0.5, (eave_l.y() + ridge.y()) * 0.5 - 20 * s,
                     ridge.x(), ridge.y() - 7 * s)
    snow_path.quadTo((eave_r.x() + ridge.x()) * 0.5, (eave_r.y() + ridge.y()) * 0.5 - 20 * s,
                     eave_r.x() + 3 * s, eave_r.y() - 4 * s)
    snow_path.quadTo((eave_r.x() + ridge.x()) * 0.5, (eave_r.y() + ridge.y()) * 0.5 + 8 * s,
                     ridge.x(), ridge.y() + 12 * s)
    snow_path.quadTo((eave_l.x() + ridge.x()) * 0.5, (eave_l.y() + ridge.y()) * 0.5 + 8 * s,
                     eave_l.x() - 3 * s, eave_l.y() - 4 * s)
    snow_grad = QLinearGradient(0, ridge.y() - 10 * s, 0, eave_y + 10 * s)
    snow_grad.setColorAt(0.0, QColor("#ffffff"))
    snow_grad.setColorAt(0.7, snow)
    snow_grad.setColorAt(1.0, QColor(pal["snow_shade"]))
    p.setBrush(QBrush(snow_grad))
    p.drawPath(snow_path)

    # Шапки снега на карнизе + сосульки.
    p.setBrush(QBrush(snow))
    for i in range(14):
        t = (i + 0.5) / 14.0
        x = eave_l.x() + (eave_r.x() - eave_l.x()) * t
        p.drawEllipse(QPointF(x, eave_y + 1 * s),
                      wall_w * 0.032, rnd.uniform(4, 8) * s)
    _icicles(p, eave_l.x() + 14 * s, eave_r.x() - 14 * s, eave_y + 6 * s, 13, rnd)

    # Труба и дым.
    chim_x = cx + 72 * s
    chim_top = top - 116 * s
    p.setBrush(QBrush(QColor(pal["wood_dark"])))
    p.drawRect(QRectF(chim_x - 13 * s, chim_top, 26 * s, 64 * s))
    pen = QPen(QColor(0, 0, 0, 60))
    pen.setWidthF(max(0.5, 0.8 * s))
    p.setPen(pen)
    for i in range(5):
        y = chim_top + 10 * s + i * 11 * s
        p.drawLine(QPointF(chim_x - 13 * s, y), QPointF(chim_x + 13 * s, y))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(snow))
    p.drawRoundedRect(QRectF(chim_x - 16 * s, chim_top - 8 * s, 32 * s, 9 * s),
                      3 * s, 3 * s)
    for i in range(7):
        radius = (8 + i * 7) * s
        p.setBrush(QBrush(QColor(222, 232, 244, max(0, 74 - i * 10))))
        p.drawEllipse(QPointF(chim_x + i * 10 * s, chim_top - 24 * s - i * 26 * s),
                      radius, radius)

    # Окна.
    for wx in (cx - 78 * s, cx + 8 * s):
        win = QRectF(wx, top + 38 * s, 44 * s, 48 * s)
        _glow(p, win.center().x(), win.center().y(), 78 * s, (255, 200, 132), 100)
        win_grad = QLinearGradient(win.left(), win.top(), win.left(), win.bottom())
        win_grad.setColorAt(0.0, QColor(255, 236, 190))
        win_grad.setColorAt(1.0, QColor(255, 196, 128))
        p.setBrush(QBrush(win_grad))
        p.drawRect(win)
        p.setPen(QPen(QColor(pal["wood_dark"]), max(1.0, 2.2 * s)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(win)
        p.drawLine(QPointF(win.center().x(), win.top()),
                   QPointF(win.center().x(), win.bottom()))
        p.drawLine(QPointF(win.left(), win.center().y()),
                   QPointF(win.right(), win.center().y()))
        p.setPen(Qt.PenStyle.NoPen)

    # Дверь.
    door = QRectF(cx - 30 * s, top + 36 * s, 44 * s, 80 * s)
    door_grad = QLinearGradient(door.left(), 0, door.right(), 0)
    door_grad.setColorAt(0.0, wood_dark.lighter(126))
    door_grad.setColorAt(1.0, wood_dark)
    p.setBrush(QBrush(door_grad))
    p.drawRoundedRect(door, 2 * s, 2 * s)
    _glow(p, door.center().x(), door.center().y(), 40 * s, (255, 198, 128), 70)
    p.setBrush(QBrush(QColor(255, 216, 156, 220)))
    p.drawRect(QRectF(door.right() - 16 * s, door.top() + 14 * s, 11 * s, 30 * s))

    # Крыльцо.
    porch_y = base_y - 4 * s
    p.setBrush(QBrush(wood_dark.lighter(114)))
    p.drawRect(QRectF(cx - 94 * s, porch_y, 188 * s, 12 * s))
    p.setBrush(QBrush(snow))
    p.drawRoundedRect(QRectF(cx - 98 * s, porch_y - 6 * s, 196 * s, 9 * s),
                      4 * s, 4 * s)
    for i in range(5):
        px = cx - 90 * s + i * 45 * s
        p.setBrush(QBrush(wood_dark))
        p.drawRect(QRectF(px, porch_y - 36 * s, 5 * s, 36 * s))
        p.setBrush(QBrush(snow))
        p.drawEllipse(QPointF(px + 2.5 * s, porch_y - 38 * s), 6.5 * s, 5.5 * s)
    p.setBrush(QBrush(wood_dark.lighter(114)))
    p.drawRect(QRectF(cx - 94 * s, porch_y - 38 * s, 188 * s, 5 * s))
    for i in range(3):
        p.setBrush(QBrush(wood_dark.lighter(104 + i * 5)))
        p.drawRect(QRectF(cx - 42 * s + i * 7 * s, porch_y + 12 * s + i * 9 * s,
                          84 * s - i * 14 * s, 8 * s))

    # Гирлянда.
    if pal["garland"]:
        _garland(p, [QPointF(eave_l.x() + 10 * s, eave_l.y() - 22 * s),
                     QPointF(cx - 62 * s, top - 94 * s),
                     QPointF(cx - 6 * s, ridge.y() + 18 * s)],
                 pal["warm"], 25 * s, s)
        _garland(p, [QPointF(cx + 6 * s, ridge.y() + 18 * s),
                     QPointF(cx + 64 * s, top - 92 * s),
                     QPointF(eave_r.x() - 10 * s, eave_r.y() - 22 * s)],
                 pal["warm"], 25 * s, s)
        _garland(p, [QPointF(cx - 94 * s, porch_y - 44 * s),
                     QPointF(cx - 46 * s, porch_y - 30 * s),
                     QPointF(cx, porch_y - 36 * s),
                     QPointF(cx + 48 * s, porch_y - 30 * s),
                     QPointF(cx + 94 * s, porch_y - 44 * s)],
                 pal["warm"], 21 * s, s)

    # Венок на фронтоне.
    wreath = QPointF(cx, top - 58 * s)
    radius = 25 * s
    _glow(p, wreath.x(), wreath.y(), 56 * s, (255, 190, 112), 80)
    pen = QPen(QColor(24, 46, 30))
    pen.setWidthF(9 * s)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(wreath, radius, radius)
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(12):
        angle = i * math.pi / 6.0
        bx = wreath.x() + math.cos(angle) * radius
        by = wreath.y() + math.sin(angle) * radius
        _glow(p, bx, by, 6.0 * s, (255, 212, 144), 120)
        p.setBrush(QBrush(QColor(255, 240, 200)))
        p.drawEllipse(QPointF(bx, by), 1.8 * s, 1.8 * s)
    _glow(p, wreath.x(), wreath.y(), 30 * s, (255, 196, 120), 55)

    # Фонарики у двери.
    for lx in (cx - 108 * s, cx + 96 * s):
        _glow(p, lx, top + 62 * s, 38 * s, (255, 192, 122), 110)
        p.setBrush(QBrush(QColor(255, 230, 176)))
        p.drawRoundedRect(QRectF(lx - 5 * s, top + 52 * s, 10 * s, 17 * s),
                          2 * s, 2 * s)


# --------------------------------------------------------------------------- #
#  Сцена
# --------------------------------------------------------------------------- #

def _paint_scene(p: QPainter, width: float, height: float, pal: dict,
                 rnd: random.Random) -> None:
    snow = pal["snow"]
    horizon = height * 0.70
    is_night = bool(pal["stars"])
    width_ref[0] = width * 0.42

    # Небо.
    sky = QLinearGradient(0, 0, 0, horizon * 1.28)
    for stop, color in pal["sky"]:
        sky.setColorAt(stop, QColor(color))
    p.fillRect(QRectF(0, 0, width, height), QBrush(sky))

    glow = pal["horizon_glow"]
    _glow(p, width * 0.44, horizon * 0.92, height * 0.66,
          (glow[0], glow[1], glow[2]), glow[3])

    # Звёзды.
    if pal["stars"]:
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(int(pal["stars"] * width / 1920)):
            x = rnd.uniform(0, width)
            y = rnd.uniform(0, horizon * 0.95)
            r = rnd.uniform(0.4, 1.4)
            fade = max(0.2, 1.0 - y / (horizon * 1.25))
            p.setBrush(QBrush(QColor(255, 255, 255, int(rnd.uniform(60, 215) * fade))))
            p.drawEllipse(QPointF(x, y), r, r)

    # Светило.
    light_x, light_y = width * 0.80, height * 0.15
    if is_night:
        _glow(p, light_x, light_y, height * 0.22, (208, 228, 255), 78)
        p.setBrush(QBrush(QColor("#f6f9ff")))
        p.drawEllipse(QPointF(light_x, light_y), height * 0.043, height * 0.043)
        p.setBrush(QBrush(QColor(226, 234, 250, 95)))
        p.drawEllipse(QPointF(light_x - height * 0.011, light_y + height * 0.011),
                      height * 0.010, height * 0.008)
        p.drawEllipse(QPointF(light_x + height * 0.014, light_y - height * 0.010),
                      height * 0.007, height * 0.006)
    else:
        _glow(p, light_x, light_y, height * 0.34, (255, 238, 200), 130)
        p.setBrush(QBrush(QColor("#fff8e8")))
        p.drawEllipse(QPointF(light_x, light_y), height * 0.050, height * 0.050)

    # Дальние планы.
    _forest(p, width, height, horizon + height * 0.004, 28,
            pal["far_trees"], snow, 0.10, 0.05, 0.12, rnd, jitter=0.005)
    fog = pal["fog"]
    fog_grad = QLinearGradient(0, horizon - height * 0.09, 0, horizon + height * 0.05)
    fog_grad.setColorAt(0.0, QColor(fog[0], fog[1], fog[2], 0))
    fog_grad.setColorAt(0.55, QColor(fog[0], fog[1], fog[2], fog[3]))
    fog_grad.setColorAt(1.0, QColor(fog[0], fog[1], fog[2], 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(fog_grad))
    p.drawRect(QRectF(0, horizon - height * 0.09, width, height * 0.14))

    _forest(p, width, height, horizon + height * 0.032, 17,
            pal["mid_trees"], snow, 0.10, 0.16, 0.42, rnd, jitter=0.008)

    # Снежное поле.
    ground = QPainterPath()
    ground.moveTo(0, height)
    ground.lineTo(0, horizon)
    ground.cubicTo(width * 0.16, horizon - height * 0.020,
                   width * 0.34, horizon + height * 0.014,
                   width * 0.52, horizon - height * 0.004)
    ground.cubicTo(width * 0.72, horizon - height * 0.024,
                   width * 0.88, horizon + height * 0.008,
                   width, horizon - height * 0.012)
    ground.lineTo(width, height)
    ground.closeSubpath()
    ground_grad = QLinearGradient(0, horizon, 0, height)
    ground_grad.setColorAt(0.0, QColor(pal["snow_shade"]))
    ground_grad.setColorAt(0.28, QColor(snow))
    ground_grad.setColorAt(1.0, QColor(pal["snow_shade"]).darker(104))
    p.setBrush(QBrush(ground_grad))
    p.drawPath(ground)

    # Сугробы на поле.
    for i in range(7):
        gx = width * (0.06 + i * 0.14) + rnd.uniform(-40, 40)
        gy = horizon + height * rnd.uniform(0.05, 0.24)
        rx = width * rnd.uniform(0.07, 0.13)
        ry = rx * rnd.uniform(0.14, 0.22)
        _glow_ellipse(p, gx, gy, rx, ry, (255, 255, 255), 60)
        _glow_ellipse(p, gx, gy + ry * 0.45, rx * 0.9, ry * 0.5,
                      (168, 194, 224), 40)

    # Изба.
    _cabin(p, width * 0.40, horizon + height * 0.115, height / 1080.0 * 1.18,
           pal, rnd)

    # Мягкое свечение вокруг избы (bloom).
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    _glow(p, width * 0.42, horizon + height * 0.02, height * 0.30,
          (72, 44, 18), 90)
    _glow(p, width * 0.42, horizon - height * 0.02, height * 0.14,
          (60, 36, 14), 70)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    # Ближний лес по краям.
    _forest(p, width, height, height * 1.0, 5, pal["near_trees"], snow,
            0.30, 0.46, 0.75, rnd, jitter=0.008)
    for x_ratio, h_ratio, tiers in ((0.03, 0.68, 5), (0.12, 0.46, 4),
                                    (0.97, 0.72, 5), (0.885, 0.44, 4)):
        _fir(p, width * x_ratio, height * 1.02, height * h_ratio,
             pal["near_trees"], snow, 0.9, rnd, tiers=tiers,
             rim=pal["warm"] if is_night else None)

    # Свет на снегу перед домом (поверх, чтобы легло на ближний план).
    _glow_ellipse(p, width * 0.42, horizon + height * 0.13, height * 0.30,
                  height * 0.09, (255, 184, 116), 34)

    # Искры на снегу.
    p.setPen(Qt.PenStyle.NoPen)
    for _ in range(int(140 * width / 1920)):
        x = rnd.uniform(0, width)
        y = rnd.uniform(horizon, height)
        p.setBrush(QBrush(QColor(255, 255, 255, rnd.randint(70, 200))))
        p.drawEllipse(QPointF(x, y), rnd.uniform(0.5, 1.4), rnd.uniform(0.5, 1.4))

    # Боке.
    for _ in range(int(24 * width / 1920)):
        x = rnd.uniform(0, width)
        y = rnd.uniform(0, height * 0.95)
        radius = rnd.uniform(8, 38)
        warm = rnd.random() < 0.4
        rgb = QColor(pal["warm"] if warm else "#cfe2ff")
        _glow(p, x, y, radius, (rgb.red(), rgb.green(), rgb.blue()),
              rnd.randint(6, 22))

    # Падающий снег.
    for _ in range(int(300 * width / 1920)):
        x = rnd.uniform(0, width)
        y = rnd.uniform(0, height)
        r = rnd.uniform(0.6, 2.5)
        p.setBrush(QBrush(QColor(255, 255, 255, rnd.randint(70, 200))))
        p.drawEllipse(QPointF(x, y), r, r)

    # Виньетка и зерно.
    if pal["vignette"]:
        vig = QRadialGradient(QPointF(width * 0.45, height * 0.54),
                              max(width, height) * 0.82)
        vig.setColorAt(0.40, QColor(0, 0, 0, 0))
        vig.setColorAt(0.76, QColor(5, 11, 22, int(pal["vignette"] * 0.30)))
        vig.setColorAt(1.0, QColor(3, 6, 12, pal["vignette"]))
        p.setBrush(QBrush(vig))
        p.drawRect(QRectF(0, 0, width, height))

    for _ in range(int(pal["grain"] * width / 1920)):
        x = rnd.uniform(0, width)
        y = rnd.uniform(0, height)
        value = 255 if rnd.random() < 0.6 else 0
        p.setBrush(QBrush(QColor(value, value, value, rnd.randint(3, 12))))
        p.drawEllipse(QPointF(x, y), 0.7, 0.7)


def render_wallpaper(width: int, height: int, variant: str = "night") -> QImage:
    width = max(640, int(width))
    height = max(480, int(height))
    pal = PALETTES.get(variant, PALETTES["night"])

    image = QImage(width, height, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    rnd = random.Random(20260101 if variant == "night" else 20260202)
    _paint_scene(painter, width, height, pal, rnd)
    painter.end()
    return image


# --------------------------------------------------------------------------- #
#  Установка на рабочий стол
# --------------------------------------------------------------------------- #

def apply_wallpaper(width: int, height: int, variant: str, settings) -> str | None:
    """Нарисовать обои, сохранить и поставить на рабочий стол."""
    try:
        image = render_wallpaper(width, height, variant)
        WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
        path = WALLPAPER_DIR / f"flake-{variant}-{width}x{height}.jpg"
        if not image.save(str(path), "JPG", 93):
            return None

        _remember_current(settings, path)
        _ensure_fill_style()
        if not winapi.set_wallpaper(str(path)):
            return None
        return str(path)
    except Exception:
        return None


def restore_wallpaper(settings) -> bool:
    previous = str(settings["wallpaper_backup"] or "")
    if not previous or not Path(previous).exists():
        return False
    return winapi.set_wallpaper(previous)


# --------------------------------------------------------------------------- #
#  Свои картинки
# --------------------------------------------------------------------------- #

def bundled_wallpapers() -> list[tuple[str, str]]:
    """Обои в комплекте: (подпись, имя файла)."""
    return [(label, name) for label, name in BUNDLED
            if (ASSETS_DIR / name).is_file()]


def apply_bundled(name: str, settings) -> str | None:
    """Поставить встроенную обоину. Файл копируется в %APPDATA%, чтобы
    после закрытия приложения Windows не потеряла картинку из temp."""
    source = ASSETS_DIR / name
    if not source.is_file():
        return None
    try:
        import shutil

        WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
        target = WALLPAPER_DIR / name
        if (not target.exists()
                or target.stat().st_size != source.stat().st_size):
            shutil.copy2(source, target)
    except OSError:
        return None
    return str(target) if apply_image(target, settings) else None


def custom_wallpapers() -> list[Path]:
    """Картинки, которые пользователь положил в папку обоев."""
    if not CUSTOM_DIR.exists():
        return []
    files = [p for p in CUSTOM_DIR.iterdir()
             if p.is_file() and p.suffix.lower() in SUPPORTED]
    return sorted(files, key=lambda p: p.name.lower())


def import_wallpaper(source: str | Path) -> Path | None:
    """Скопировать выбранную картинку в папку обоев приложения."""
    src = Path(source)
    if not src.is_file() or src.suffix.lower() not in SUPPORTED:
        return None
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    target = CUSTOM_DIR / src.name
    try:
        if src.resolve() == target.resolve():
            return target
    except OSError:
        pass
    counter = 1
    while target.exists():
        target = CUSTOM_DIR / f"{src.stem}-{counter}{src.suffix}"
        counter += 1
    try:
        import shutil

        shutil.copy2(src, target)
    except OSError:
        return None
    return target


def apply_image(path: str | Path, settings) -> bool:
    """Поставить обоями любую картинку (и запомнить прежние обои)."""
    target = Path(path)
    if not target.is_file():
        return False
    _remember_current(settings, target)
    _ensure_fill_style()
    return winapi.set_wallpaper(str(target))


def _remember_current(settings, new_path: Path) -> None:
    current = winapi.current_wallpaper()
    if current and current.lower() != str(new_path).lower():
        settings["wallpaper_backup"] = current


def _ensure_fill_style() -> None:
    """Режим «заполнить» — чтобы картинка не растягивалась и не мозаичилась."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop",
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, "10")
            winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, "0")
    except OSError:
        pass

"""Новогодние обои: рисуем зимнюю сцену и ставим её на рабочий стол."""
from __future__ import annotations

import math
import os
import random
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPolygonF, QRadialGradient)

from . import winapi
from .settings import APP_DIR

WALLPAPER_DIR = APP_DIR / "wallpaper"

PALETTES = {
    "night": {
        "sky": [(0.0, "#050b18"), (0.42, "#0e1f3a"), (0.72, "#1d3c5e"), (1.0, "#3b6484")],
        "stars": True,
        "aurora": True,
        "moon": "#f6f8ff",
        "hill_far": "#1a2f4a",
        "hill_mid": "#16283e",
        "hill_near": "#0e1b2c",
        "snow": "#eef5ff",
        "tree_far": "#122234",
        "tree_near": "#0a1422",
        "house": "#2a2233",
        "roof": "#1b1622",
        "window": "#ffcf72",
        "vignette": 150,
    },
    "frost": {
        "sky": [(0.0, "#6f9cc4"), (0.42, "#a3c6e0"), (0.76, "#cde2f1"), (1.0, "#eaf4fc")],
        "stars": False,
        "aurora": False,
        "sun": True,
        "moon": "#fff6dc",
        "hill_far": "#a9c4d8",
        "hill_mid": "#93b2c9",
        "hill_near": "#e6f1f9",
        "snow": "#ffffff",
        "tree_far": "#6b879f",
        "tree_near": "#46607a",
        "house": "#7d4c35",
        "roof": "#5d3627",
        "window": "#ffe6a3",
        "vignette": 60,
    },
}


def _fir(p: QPainter, x: float, base_y: float, height: float,
         color: str, snow: str, snow_amount: float = 0.55) -> None:
    """Ёлка из трёх ярусов с шапками снега."""
    trunk = QRectF(x - max(1.2, height * 0.018), base_y - height * 0.12,
                   max(2.4, height * 0.036), height * 0.14)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(color).darker(135)))
    p.drawRect(trunk)

    apex = base_y - height
    tiers = 3
    for i in range(tiers):
        top = apex + height * (0.08 + i * 0.22)
        bottom = min(apex + height * (0.44 + i * 0.22), base_y)
        half = height * 0.12 * (1.0 + i * 0.85)
        poly = QPolygonF([
            QPointF(x, top),
            QPointF(x - half, bottom),
            QPointF(x + half, bottom),
        ])
        p.setBrush(QBrush(QColor(color)))
        p.drawPolygon(poly)

        # Шапка снега лежит на ярусе — треугольник от той же верхушки.
        if snow_amount > 0.05:
            snow_h = (bottom - top) * (0.30 + snow_amount * 0.18)
            cap = QPolygonF([
                QPointF(x, top),
                QPointF(x - half * 0.62, top + snow_h),
                QPointF(x - half * 0.20, top + snow_h * 0.86),
                QPointF(x + half * 0.24, top + snow_h * 0.94),
                QPointF(x + half * 0.64, top + snow_h),
            ])
            snow_color = QColor(snow)
            snow_color.setAlphaF(min(1.0, 0.60 + snow_amount * 0.40))
            p.setBrush(QBrush(snow_color))
            p.drawPolygon(cap)


def _house(p: QPainter, x: float, base_y: float, scale: float, palette: dict) -> None:
    w, h = 140 * scale, 86 * scale
    p.setPen(Qt.PenStyle.NoPen)

    # Стена.
    body = QRectF(x - w * 0.5, base_y - h, w, h)
    p.setBrush(QBrush(QColor(palette["house"])))
    p.drawRect(body)
    p.setBrush(QBrush(QColor(palette["house"]).darker(112)))
    p.drawRect(QRectF(body.left(), body.top(), w, 6 * scale))

    # Крыша.
    roof = QPolygonF([
        QPointF(x - 96 * scale, base_y - 84 * scale),
        QPointF(x, base_y - 162 * scale),
        QPointF(x + 96 * scale, base_y - 84 * scale),
    ])
    p.setBrush(QBrush(QColor(palette["roof"])))
    p.drawPolygon(roof)

    # Снег лежит по скатам крыши.
    snow_pen = QPen(QColor(palette["snow"]))
    snow_pen.setWidthF(11 * scale)
    snow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    snow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(snow_pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolyline(QPolygonF([
        QPointF(x - 92 * scale, base_y - 88 * scale),
        QPointF(x, base_y - 166 * scale),
        QPointF(x + 92 * scale, base_y - 88 * scale),
    ]))
    p.setPen(Qt.PenStyle.NoPen)

    # Труба с дымом.
    p.setBrush(QBrush(QColor(palette["roof"]).darker(118)))
    p.drawRect(QRectF(x + 34 * scale, base_y - 148 * scale, 17 * scale, 46 * scale))
    p.setBrush(QBrush(QColor(palette["snow"])))
    p.drawRect(QRectF(x + 31 * scale, base_y - 152 * scale, 23 * scale, 7 * scale))
    for i in range(4):
        radius = (9 + i * 5) * scale
        p.setBrush(QBrush(QColor(230, 238, 248, max(0, 80 - i * 18))))
        p.drawEllipse(QPointF(x + 44 * scale + i * 8 * scale,
                              base_y - 164 * scale - i * 25 * scale),
                      radius, radius)

    # Окна с тёплым светом.
    for wx in (x - 44 * scale, x + 16 * scale):
        win = QRectF(wx, base_y - 62 * scale, 26 * scale, 28 * scale)
        glow = QRadialGradient(win.center(), 44 * scale)
        warm = QColor(palette["window"])
        glow.setColorAt(0.0, QColor(warm.red(), warm.green(), warm.blue(), 70))
        glow.setColorAt(1.0, QColor(warm.red(), warm.green(), warm.blue(), 0))
        p.setBrush(QBrush(glow))
        p.drawEllipse(win.center(), 40 * scale, 36 * scale)
        p.setBrush(QBrush(warm))
        p.drawRect(win)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(palette["roof"]).darker(140), 1.6 * scale))
        p.drawRect(win)
        p.drawLine(QPointF(win.center().x(), win.top()),
                   QPointF(win.center().x(), win.bottom()))
        p.drawLine(QPointF(win.left(), win.center().y()),
                   QPointF(win.right(), win.center().y()))
        p.setPen(Qt.PenStyle.NoPen)

    # Дверь и сугроб у крыльца.
    door = QRectF(x - 13 * scale, base_y - 46 * scale, 26 * scale, 46 * scale)
    p.setBrush(QBrush(QColor(palette["roof"]).lighter(118)))
    p.drawRoundedRect(door, 2 * scale, 2 * scale)
    p.setBrush(QBrush(QColor(palette["snow"])))
    p.drawEllipse(QPointF(x - 52 * scale, base_y + 2 * scale), 34 * scale, 11 * scale)
    p.drawEllipse(QPointF(x + 34 * scale, base_y + 2 * scale), 40 * scale, 12 * scale)


def render_wallpaper(width: int, height: int, variant: str = "night") -> QImage:
    palette = PALETTES.get(variant, PALETTES["night"])
    width = max(640, int(width))
    height = max(480, int(height))

    image = QImage(width, height, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    rnd = random.Random(20260101 if variant == "night" else 20260202)

    # Небо.
    sky = QLinearGradient(0, 0, 0, height)
    for stop, color in palette["sky"]:
        sky.setColorAt(stop, QColor(color))
    painter.fillRect(QRectF(0, 0, width, height), QBrush(sky))

    # Звёзды: мелкая крошка плюс редкие яркие с лучиками.
    if palette["stars"]:
        painter.setPen(Qt.PenStyle.NoPen)
        for _ in range(int(width * height / 4200)):
            x = rnd.uniform(0, width)
            y = rnd.uniform(0, height * 0.74)
            r = rnd.uniform(0.35, 1.15)
            fade = max(0.15, 1.0 - y / (height * 0.95))
            painter.setBrush(QBrush(QColor(255, 255, 255, int(rnd.uniform(70, 235) * fade))))
            painter.drawEllipse(QPointF(x, y), r, r)
        for _ in range(max(6, int(width / 190))):
            x = rnd.uniform(0, width)
            y = rnd.uniform(height * 0.03, height * 0.55)
            r = rnd.uniform(1.0, 1.7)
            painter.setBrush(QBrush(QColor(255, 255, 255, 245)))
            painter.drawEllipse(QPointF(x, y), r, r)
            ray = QPen(QColor(215, 232, 255, 130))
            ray.setWidthF(0.9)
            painter.setPen(ray)
            painter.drawLine(QPointF(x - r * 3.2, y), QPointF(x + r * 3.2, y))
            painter.drawLine(QPointF(x, y - r * 3.2), QPointF(x, y + r * 3.2))
            painter.setPen(Qt.PenStyle.NoPen)

    # Северное сияние: мягкие полосы из перекрывающихся штрихов.
    if palette["aurora"]:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for band, color in enumerate(((110, 240, 195), (150, 175, 255))):
            base_y = height * (0.11 + band * 0.055)
            for k in range(5):
                offset = (k - 2) * height * 0.012
                path = QPainterPath()
                path.moveTo(-40, base_y + offset)
                path.cubicTo(width * 0.30, base_y - height * 0.075 + offset,
                             width * 0.62, base_y + height * 0.055 + offset,
                             width + 40, base_y - height * 0.02 + offset)
                pen = QPen(QColor(color[0], color[1], color[2], 11 - abs(k - 2) * 2))
                pen.setWidthF(height * (0.035 + 0.012 * (2 - abs(k - 2))))
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)

    # Светило: луна ночью, солнце морозным утром.
    moon_x = width * 0.79
    moon_y = height * 0.17
    is_sun = bool(palette.get("sun"))
    moon_r = height * (0.052 if is_sun else 0.048)
    halo = QRadialGradient(QPointF(moon_x, moon_y), moon_r * (8.0 if is_sun else 7.0))
    if is_sun:
        halo.setColorAt(0.0, QColor(255, 246, 214, 150))
        halo.setColorAt(0.32, QColor(255, 236, 190, 62))
        halo.setColorAt(1.0, QColor(255, 240, 205, 0))
    else:
        halo.setColorAt(0.0, QColor(255, 255, 255, 110))
        halo.setColorAt(0.32, QColor(225, 238, 255, 45))
        halo.setColorAt(1.0, QColor(210, 230, 255, 0))
    painter.setBrush(QBrush(halo))
    painter.drawEllipse(QPointF(moon_x, moon_y), moon_r * (8.0 if is_sun else 7.0),
                        moon_r * (8.0 if is_sun else 7.0))
    painter.setBrush(QBrush(QColor(palette["moon"])))
    painter.drawEllipse(QPointF(moon_x, moon_y), moon_r, moon_r)
    if not is_sun:
        painter.setBrush(QBrush(QColor(226, 233, 246, 90)))
        painter.drawEllipse(QPointF(moon_x - moon_r * 0.3, moon_y + moon_r * 0.25),
                            moon_r * 0.22, moon_r * 0.18)
        painter.drawEllipse(QPointF(moon_x + moon_r * 0.28, moon_y - moon_r * 0.3),
                            moon_r * 0.15, moon_r * 0.12)

    # Дальние холмы.
    def hills(color: str, top_ratio: float, amp: float, phase: float) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.moveTo(0, height)
        path.lineTo(0, height * top_ratio)
        steps = 14
        for i in range(steps + 1):
            t = i / steps
            y = height * top_ratio - math.sin(t * math.pi * 1.4 + phase) * height * amp
            path.lineTo(width * t, y)
        path.lineTo(width, height)
        path.closeSubpath()
        painter.setBrush(QBrush(QColor(color)))
        painter.drawPath(path)

    hills(palette["hill_far"], 0.72, 0.035, 0.4)
    hills(palette["hill_mid"], 0.80, 0.028, 2.1)
    hills(palette["hill_near"], 0.90, 0.022, 4.4)

    # Ёлки на дальнем плане.
    for _ in range(16):
        x = rnd.uniform(0, width)
        base = height * rnd.uniform(0.80, 0.86)
        h = height * rnd.uniform(0.07, 0.13)
        _fir(painter, x, base, h, palette["tree_far"], palette["snow"], 0.5)

    # Ёлки ближе.
    for _ in range(9):
        x = rnd.uniform(-0.02, 1.02) * width
        base = height * rnd.uniform(0.90, 0.96)
        h = height * rnd.uniform(0.12, 0.20)
        _fir(painter, x, base, h, palette["tree_near"], palette["snow"], 0.7)

    # Домик.
    _house(painter, width * 0.30, height * 0.855, height / 1080.0 * 1.15, palette)

    # Передний сугроб.
    snow = QPainterPath()
    snow.moveTo(0, height)
    snow.lineTo(0, height * 0.955)
    snow.cubicTo(width * 0.22, height * 0.912,
                 width * 0.42, height * 0.975,
                 width * 0.62, height * 0.948)
    snow.cubicTo(width * 0.80, height * 0.925,
                 width * 0.92, height * 0.96,
                 width, height * 0.938)
    snow.lineTo(width, height)
    snow.closeSubpath()
    snow_grad = QLinearGradient(0, height * 0.90, 0, height)
    snow_grad.setColorAt(0.0, QColor(palette["snow"]))
    snow_grad.setColorAt(1.0, QColor(palette["snow"]).darker(112))
    painter.setBrush(QBrush(snow_grad))
    painter.drawPath(snow)

    # Блёстки на снегу.
    for _ in range(int(width * height / 26000)):
        x = rnd.uniform(0, width)
        y = rnd.uniform(height * 0.90, height * 0.99)
        painter.setBrush(QBrush(QColor(255, 255, 255, rnd.randint(60, 170))))
        painter.drawEllipse(QPointF(x, y), rnd.uniform(0.6, 1.6), rnd.uniform(0.6, 1.6))

    # Виньетка.
    vig_alpha = palette["vignette"]
    if vig_alpha:
        vig = QRadialGradient(QPointF(width * 0.5, height * 0.52),
                              max(width, height) * 0.78)
        vig.setColorAt(0.55, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(0, 0, 0, vig_alpha))
        painter.setBrush(QBrush(vig))
        painter.drawRect(QRectF(0, 0, width, height))

    painter.end()
    return image


def apply_wallpaper(width: int, height: int, variant: str, settings) -> str | None:
    """Нарисовать обои, сохранить и поставить на рабочий стол."""
    try:
        image = render_wallpaper(width, height, variant)
        WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
        path = WALLPAPER_DIR / f"flake-{variant}-{width}x{height}.jpg"
        if not image.save(str(path), "JPG", 93):
            return None

        current = winapi.current_wallpaper()
        if current and current.lower() != str(path).lower():
            settings["wallpaper_backup"] = current

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

"""Отрисовка Flake для Windows через QPainter.

Визуал повторяет Metal-шейдеры оригинала: кристаллические снежинки,
подсвеченные шары, сугробы с холодной тенью у основания.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage,
                           QLinearGradient, QPainter, QPainterPath, QPen,
                           QPolygonF, QRadialGradient)

from .sim import Simulator, Snowball, Snowman

FLAKE_MAX_SPRITE = 28


# --------------------------------------------------------------------------- #
#  Спрайты снежинок
# --------------------------------------------------------------------------- #

class SpriteCache:
    def __init__(self) -> None:
        self._cache: dict[tuple[int, int], QImage] = {}

    def flake(self, diameter: int, variant: int) -> QImage:
        d = max(3, min(FLAKE_MAX_SPRITE, int(diameter)))
        key = (d, variant)
        img = self._cache.get(key)
        if img is None:
            img = self._build(d, variant)
            self._cache[key] = img
        return img

    # ------------------------------------------------------------------ #
    @staticmethod
    def _build(size: int, variant: int) -> QImage:
        img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = size / 2.0
        radius = c - 0.35

        # Голубое свечение вокруг кристалла.
        bloom = QRadialGradient(c, c, max(0.6, radius))
        bloom.setColorAt(0.0, QColor(236, 245, 255, 110))
        bloom.setColorAt(0.45, QColor(206, 226, 255, 46))
        bloom.setColorAt(1.0, QColor(200, 220, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bloom))
        p.drawEllipse(QPointF(c, c), radius, radius)

        if size >= 7:
            # Шесть лучей с короткими боковыми веточками — как в шейдере.
            angle0 = variant * (math.pi / 6.0)
            arm_pen = QPen(QColor(238, 246, 255, 165))
            arm_pen.setWidthF(max(0.75, size * 0.055))
            arm_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(arm_pen)
            for k in range(6):
                a = angle0 + k * math.pi / 3.0
                dx, dy = math.cos(a), math.sin(a)
                p.drawLine(QPointF(c + dx * radius * 0.16, c + dy * radius * 0.16),
                           QPointF(c + dx * radius * 0.94, c + dy * radius * 0.94))
                if size >= 11:
                    for t, sign in ((0.52, 1.0), (0.72, -1.0)):
                        bx = c + dx * radius * t
                        by = c + dy * radius * t
                        ba = a + sign * 0.62
                        ln = radius * 0.26
                        p.drawLine(QPointF(bx, by),
                                   QPointF(bx + math.cos(ba) * ln,
                                           by + math.sin(ba) * ln))

        # Яркое ядро.
        core = QRadialGradient(c, c, max(0.6, radius * 0.62))
        core.setColorAt(0.0, QColor(255, 255, 255, 250))
        core.setColorAt(0.45, QColor(246, 251, 255, 165))
        core.setColorAt(1.0, QColor(240, 248, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(c, c), radius * 0.62, radius * 0.62)
        p.end()
        return img


# --------------------------------------------------------------------------- #
#  Рендерер
# --------------------------------------------------------------------------- #

class Renderer:
    def __init__(self) -> None:
        self.sprites = SpriteCache()
        self._snow_font = QFont("Segoe UI", 8)
        self._snow_font.setBold(True)

    # ------------------------------------------------------------------ #
    def draw(self, p: QPainter, sim: Simulator, dpr: float,
             screen_rect: QRectF) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        blocked = [a for a in sim.snapshot.blocked]
        if blocked:
            path = QPainterPath()
            path.addRect(screen_rect)
            for area in blocked:
                cut = QPainterPath()
                cut.addRect(area)
                path = path.subtracted(cut)
            p.setClipPath(path)
        else:
            p.setClipRect(screen_rect)

        self._draw_drifts(p, sim, dpr, screen_rect)
        self._draw_train(p, sim)
        self._draw_flakes(p, sim, dpr, screen_rect)
        self._draw_snowmen(p, sim)
        self._draw_balls(p, sim)

    # ------------------------------------------------------------------ #
    def _draw_train(self, p: QPainter, sim: Simulator) -> None:
        train = sim.train_runner.train
        if train is None:
            return

        # Дым из трубы.
        p.setPen(Qt.PenStyle.NoPen)
        for puff in train.puffs:
            fade = max(0.0, min(1.0, puff.life / puff.max_life))
            p.setBrush(QBrush(QColor(226, 233, 244, int(105 * fade))))
            p.drawEllipse(QPointF(puff.x, puff.y), puff.size, puff.size)

        p.save()
        p.translate(train.x, train.rail_y)
        # Локальная схема нарисована «отвалом влево», поэтому при движении
        # вправо её надо отразить.
        p.scale(-float(train.direction), 1.0)

        # Вагонетка позади локомотива (в локальных координатах — за будкой).
        p.setBrush(QBrush(QColor(52, 64, 82)))
        p.drawRoundedRect(QRectF(80, -30, 34, 21), 3, 3)
        p.setBrush(QBrush(QColor(248, 251, 255)))
        p.drawRoundedRect(QRectF(80, -33, 34, 6), 3, 3)
        p.setBrush(QBrush(QColor(72, 86, 106)))
        p.drawRect(QRectF(86, -26, 8, 12))
        p.drawRect(QRectF(98, -26, 8, 12))

        # Отвал впереди.
        p.setBrush(QBrush(QColor(176, 184, 196)))
        p.drawPolygon(QPolygonF([
            QPointF(2, -2), QPointF(30, -2), QPointF(24, -30), QPointF(4, -20),
        ]))
        p.setBrush(QBrush(QColor(122, 132, 148)))
        p.drawPolygon(QPolygonF([QPointF(2, -2), QPointF(11, -2), QPointF(7, -15)]))
        p.setBrush(QBrush(QColor(252, 254, 255)))
        p.drawPolygon(QPolygonF([
            QPointF(24, -30), QPointF(29, -22), QPointF(25, -18), QPointF(21, -25),
        ]))

        # Котёл.
        p.setBrush(QBrush(QColor(150, 46, 46)))
        p.drawRoundedRect(QRectF(16, -34, 48, 25), 5, 5)
        p.setBrush(QBrush(QColor(214, 178, 92)))
        p.drawRect(QRectF(31, -34, 3, 25))
        p.drawRect(QRectF(47, -34, 3, 25))
        p.setBrush(QBrush(QColor(238, 246, 255)))
        p.drawRoundedRect(QRectF(18, -37, 44, 5), 2.5, 2.5)

        # Будка.
        p.setBrush(QBrush(QColor(126, 38, 38)))
        p.drawRoundedRect(QRectF(50, -52, 22, 43), 3, 3)
        p.setBrush(QBrush(QColor(88, 28, 28)))
        p.drawRoundedRect(QRectF(48, -56, 26, 6), 2, 2)
        p.setBrush(QBrush(QColor(250, 253, 255)))
        p.drawRoundedRect(QRectF(47, -59, 28, 4.5), 2, 2)
        p.setBrush(QBrush(QColor(255, 214, 120)))
        p.drawRoundedRect(QRectF(55, -46, 12, 11), 2, 2)
        p.setBrush(QBrush(QColor(255, 240, 190)))
        p.drawRoundedRect(QRectF(57, -44, 8, 7), 1, 1)

        # Труба.
        p.setBrush(QBrush(QColor(60, 60, 66)))
        p.drawRect(QRectF(22, -46, 9, 13))
        p.setBrush(QBrush(QColor(40, 40, 46)))
        p.drawRoundedRect(QRectF(20, -49, 13, 4), 1.5, 1.5)
        p.setBrush(QBrush(QColor(252, 254, 255)))
        p.drawRoundedRect(QRectF(19, -51.5, 15, 3.5), 1.5, 1.5)

        # Фара и её отсвет.
        p.setBrush(QBrush(QColor(255, 236, 170, 90)))
        p.drawEllipse(QPointF(20, -26), 6.5, 6.5)
        p.setBrush(QBrush(QColor(255, 244, 205)))
        p.drawEllipse(QPointF(17, -26), 3.0, 3.0)

        # Колёса.
        for cx, cy, radius in ((28.0, -9.0, 8.5), (46.0, -9.0, 8.5),
                               (64.0, -7.0, 6.0), (88.0, -9.0, 7.5),
                               (102.0, -9.0, 7.5)):
            p.setBrush(QBrush(QColor(36, 38, 44)))
            p.drawEllipse(QPointF(cx, cy), radius, radius)
            p.setBrush(QBrush(QColor(122, 128, 138)))
            p.drawEllipse(QPointF(cx, cy), radius * 0.55, radius * 0.55)
            pen = QPen(QColor(72, 76, 84))
            pen.setWidthF(1.2)
            p.setPen(pen)
            for k in range(3):
                angle = train.wheel + k * math.pi / 3.0
                p.drawLine(
                    QPointF(cx - math.cos(angle) * radius * 0.8,
                            cy - math.sin(angle) * radius * 0.8),
                    QPointF(cx + math.cos(angle) * radius * 0.8,
                            cy + math.sin(angle) * radius * 0.8),
                )
            p.setPen(Qt.PenStyle.NoPen)

        p.restore()

    # ------------------------------------------------------------------ #
    def _draw_flakes(self, p: QPainter, sim: Simulator, dpr: float,
                     screen_rect: QRectF) -> None:
        f = sim.field
        if f.count == 0:
            return
        left = screen_rect.left() - 30
        right = screen_rect.right() + 30
        top = screen_rect.top() - 30
        bottom = screen_rect.bottom() + 30

        xs = f.x.tolist()
        ys = f.y.tolist()
        sizes = f.size.tolist()
        ops = f.opacity.tolist()
        phases = f.phase.tolist()

        for x, y, size, op, ph in zip(xs, ys, sizes, ops, phases):
            if x < left or x > right or y < top or y > bottom:
                continue
            diameter = size * 2.0
            if diameter < 2.0:
                diameter = 2.0
            variant = int(ph * 7.0) % 4
            sprite = self.sprites.flake(int(round(diameter * dpr)), variant)
            half = (sprite.width() / dpr) * 0.5
            p.setOpacity(max(0.05, min(1.0, op)))
            p.drawImage(QRectF(x - half, y - half, half * 2, half * 2), sprite)
        p.setOpacity(1.0)

    # ------------------------------------------------------------------ #
    def _draw_drifts(self, p: QPainter, sim: Simulator, dpr: float,
                     screen_rect: QRectF) -> None:
        active = sim.active_surface_ids()
        for lid, surface in sim.surfaces.items():
            if lid not in active:
                continue
            if surface.h.size == 0 or float(surface.h.max()) < 0.18:
                continue
            if (surface.top < screen_rect.top() - 40
                    or surface.top > screen_rect.bottom() + 40):
                continue
            if (surface.x > screen_rect.right() + 10
                    or surface.x + surface.width < screen_rect.left() - 10):
                continue
            self._draw_surface(p, surface, screen_rect)

    @staticmethod
    def _blur(values: list[float], passes: int = 2) -> list[float]:
        out = list(values)
        n = len(out)
        if n < 3:
            return out
        for _ in range(passes):
            prev = list(out)
            for i in range(1, n - 1):
                out[i] = prev[i - 1] * 0.25 + prev[i] * 0.5 + prev[i + 1] * 0.25
        return out

    def _draw_surface(self, p: QPainter, surface, screen_rect: QRectF) -> None:
        h = surface.h
        cell = surface.cell
        n = h.size
        if n < 2:
            return

        corner = surface.corner
        base_y = surface.top

        profile: list[tuple[float, float]] = []
        for i in range(n):
            local = i * cell
            if local < 0.5 or local > surface.width - 0.5:
                continue
            height = float(h[i])
            if height <= 0.05:
                continue
            dist = min(local, surface.width - local)
            if dist < corner:
                t = max(0.0, dist - 0.5) / max(0.5, corner - 0.5)
                height *= t * t * (3.0 - 2.0 * t)
            if height <= 0.05:
                continue
            profile.append((surface.x + local, height))

        if len(profile) < 2:
            return

        # Сглаживание гребня: несколько проходов «1-2-1» — сугроб, а не гистограмма.
        heights = [ph for _, ph in profile]
        xs = [px for px, _ in profile]
        smoothed = self._blur(heights, 3)
        peak = max(smoothed) if smoothed else 1.0

        poly = QPolygonF()
        poly.append(QPointF(xs[0], base_y))
        for px, hh in zip(xs, smoothed):
            poly.append(QPointF(px, base_y - hh))
        poly.append(QPointF(xs[-1], base_y))
        poly.append(QPointF(xs[0], base_y))

        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()

        top_y = base_y - max(peak, 1.0)
        grad = QLinearGradient(0, top_y, 0, base_y)
        grad.setColorAt(0.0, QColor(255, 255, 255, 250))
        grad.setColorAt(0.55, QColor(246, 250, 255, 245))
        grad.setColorAt(1.0, QColor(214, 227, 247, 236))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(path)

        # Тёплый блик по гребню.
        crest = QPainterPath()
        crest.moveTo(xs[0], base_y - smoothed[0])
        for px, hh in zip(xs[1:], smoothed[1:]):
            crest.lineTo(px, base_y - hh)
        pen = QPen(QColor(255, 255, 255, 205))
        pen.setWidthF(1.1)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(crest)

        # Мягкая тень под кромкой — снег лежит на окне, а не парит.
        shadow = QPen(QColor(150, 176, 210, 60))
        shadow.setWidthF(1.4)
        p.setPen(shadow)
        p.drawLine(QPointF(xs[0], base_y + 0.8), QPointF(xs[-1], base_y + 0.8))

    # ------------------------------------------------------------------ #
    def _draw_balls(self, p: QPainter, sim: Simulator) -> None:
        for ball in sim.balls:
            self._sphere(p, ball.x, ball.y, ball.radius)

    def _sphere(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        if r < 0.6:
            return
        grad = QRadialGradient(cx - r * 0.34, cy - r * 0.40, max(0.8, r * 1.62))
        grad.setColorAt(0.0, QColor(255, 255, 255, 255))
        grad.setColorAt(0.38, QColor(251, 253, 255, 255))
        grad.setColorAt(0.72, QColor(232, 240, 252, 255))
        grad.setColorAt(0.92, QColor(203, 217, 238, 255))
        grad.setColorAt(1.0, QColor(188, 204, 229, 235))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Мягкая кромка-«пух».
        halo = QRadialGradient(cx, cy, r * 1.05)
        halo.setColorAt(0.88, QColor(255, 255, 255, 0))
        halo.setColorAt(0.97, QColor(255, 255, 255, 38))
        halo.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), r * 1.06, r * 1.06)

    # ------------------------------------------------------------------ #
    def _draw_snowmen(self, p: QPainter, sim: Simulator) -> None:
        for man in sim.snowmen:
            self._draw_snowman(p, man)

    def _draw_snowman(self, p: QPainter, man: Snowman) -> None:
        bx, by = man.pose_base
        mx, my = man.pose_mid
        hx, hy = man.pose_head
        base_r, mid_r, head_r = man.base_r, man.mid_r, man.head_r

        # Руки рисуем до шаров, чтобы казались за телом.
        self._draw_arm(p, man, left=True)
        self._draw_arm(p, man, left=False)

        self._sphere(p, bx, by, base_r)
        self._sphere(p, mx, my, mid_r)
        self._sphere(p, hx, hy, head_r)

        coal = QColor(20, 20, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(coal))

        eye = max(1.4, min(3.4, head_r * 0.22))
        p.drawEllipse(QPointF(hx - head_r * 0.28, hy - head_r * 0.12), eye * 0.5, eye * 0.5)
        p.drawEllipse(QPointF(hx + head_r * 0.28, hy - head_r * 0.12), eye * 0.5, eye * 0.5)

        smile = max(0.9, eye * 0.55)
        for i in range(-2, 3):
            t = i / 2.0
            sx = hx + t * head_r * 0.28
            sy = hy + head_r * 0.28 + (1 - abs(t)) * head_r * 0.08
            p.drawEllipse(QPointF(sx, sy), smile * 0.5, smile * 0.5)

        btn = max(1.4, min(3.0, mid_r * 0.16))
        for dy in (-0.35, 0.05, 0.42):
            p.drawEllipse(QPointF(mx, my + mid_r * dy), btn * 0.5, btn * 0.5)
        base_btn = max(1.6, min(3.2, base_r * 0.12))
        p.drawEllipse(QPointF(bx, by + base_r * 0.25), base_btn * 0.5, base_btn * 0.5)

        # Морковка.
        p.setBrush(QBrush(QColor(255, 122, 20)))
        nose = QPolygonF([
            QPointF(hx + head_r * 0.08, hy + head_r * 0.02 - head_r * 0.14),
            QPointF(hx + head_r * 0.08, hy + head_r * 0.02 + head_r * 0.14),
            QPointF(hx + head_r * 0.08 + head_r * 0.9, hy + head_r * 0.02),
        ])
        p.drawPolygon(nose)

        self._draw_bucket(p, man)
        if man.sign_text.strip():
            self._draw_sign(p, man)

        # Снежок в руке во время замаха.
        if man.throw_t > 0.0 and not man.throw_released and man.throw_t < 0.48:
            tx, ty = man.arm_tip(man.throw_side < 0)
            self._sphere(p, tx, ty, max(4.5, min(7.5, man.mid_r * 0.38)))

    def _draw_arm(self, p: QPainter, man: Snowman, left: bool) -> None:
        brown = QColor(102, 61, 31)
        sx, sy = man.arm_shoulder(left)
        ex, ey = man.arm_tip(left)
        d = -1.0 if left else 1.0
        angle = man.arm_angle(left)
        length = man.mid_r * 1.35

        pen = QPen(brown)
        pen.setWidthF(max(1.1, man.mid_r * 0.10))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(sx, sy), QPointF(ex, ey))

        mx = sx + (ex - sx) * 0.58
        my = sy + (ey - sy) * 0.58
        fx = d * math.cos(angle)
        fy = -math.sin(angle)
        px = -fy * d
        py = fx * d
        thin = QPen(brown)
        thin.setWidthF(max(0.8, man.mid_r * 0.075))
        thin.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(thin)
        p.drawLine(
            QPointF(mx, my),
            QPointF(mx + fx * length * 0.38 + px * length * 0.12,
                    my + fy * length * 0.38 + py * length * 0.12),
        )
        p.drawLine(
            QPointF(mx + fx * length * 0.12, my + fy * length * 0.12),
            QPointF(mx + fx * length * 0.34 - px * length * 0.22,
                    my + fy * length * 0.34 - py * length * 0.22),
        )

    def _draw_bucket(self, p: QPainter, man: Snowman) -> None:
        hx, hy = man.pose_head
        head_r = man.head_r
        bottom = hy - head_r * 0.45
        side = head_r * 1.05
        height = head_r * 1.05

        p.setPen(Qt.PenStyle.NoPen)
        body = QRectF(hx - side, bottom - height, side * 2, height)
        grad = QLinearGradient(body.left(), 0, body.right(), 0)
        grad.setColorAt(0.0, QColor(118, 124, 133))
        grad.setColorAt(0.35, QColor(148, 155, 165))
        grad.setColorAt(1.0, QColor(96, 102, 112))
        p.setBrush(QBrush(grad))
        p.drawRect(body)

        lip = side * 1.12
        p.setBrush(QBrush(QColor(178, 184, 194)))
        p.drawRect(QRectF(hx - lip, bottom - height - 2.2, lip * 2, 3.6))

        band_y = bottom - height * 0.45
        p.setBrush(QBrush(QColor(84, 90, 99)))
        p.drawRect(QRectF(hx - side, band_y - 1.2, side * 2, 2.4))

        pen = QPen(QColor(84, 90, 99))
        pen.setWidthF(max(1.0, head_r * 0.09))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        hx_off = side * 0.62
        top = bottom - height - head_r * 0.55
        p.drawLine(QPointF(hx - hx_off, bottom - height * 0.45), QPointF(hx - hx_off, top))
        p.drawLine(QPointF(hx + hx_off, bottom - height * 0.45), QPointF(hx + hx_off, top))
        p.drawLine(QPointF(hx - hx_off, top), QPointF(hx + hx_off, top))

    def _draw_sign(self, p: QPainter, man: Snowman) -> None:
        text = man.sign_text.strip()
        if not text:
            return
        ax, ay = man.sign_anchor

        font = QFont("Segoe UI", 9)
        font.setBold(True)
        font.setPointSizeF(max(7.0, min(12.0, man.mid_r * 0.62)))
        fm = QFontMetricsF(font)
        pad_x, pad_y = 6.0, 4.0
        max_w = max(46.0, man.mid_r * 6.0)
        tw = fm.horizontalAdvance(text)
        if tw + pad_x * 2 > max_w:
            text = fm.elidedText(text, Qt.TextElideMode.ElideRight, max_w - pad_x * 2)
            tw = fm.horizontalAdvance(text)
        w = max(26.0, tw + pad_x * 2)
        h = max(16.0, fm.height() + pad_y * 2)
        hand_x, hand_y = man.arm_tip(False)
        # Табличка висит на руке и не закрывает туловище.
        rect = QRectF(hand_x - 3.0, ay - h * 0.5, w, h)

        # Шест от руки к табличке.
        stick = QPen(QColor(102, 61, 31))
        stick.setWidthF(1.5)
        stick.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(stick)
        p.drawLine(QPointF(hand_x, hand_y), QPointF(rect.left() + 3, rect.center().y() + h * 0.25))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(186, 143, 84)))
        p.drawRoundedRect(rect, 2.0, 2.0)
        p.setBrush(QBrush(QColor(214, 176, 118)))
        p.drawRoundedRect(rect.adjusted(1.8, 1.8, -1.8, -1.8), 1.2, 1.2)

        p.setFont(font)
        p.setPen(QPen(QColor(74, 46, 20)))
        p.drawText(rect.adjusted(pad_x * 0.5, 0, -pad_x * 0.5, 0),
                   int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextSingleLine),
                   text)

"""Сугроб на кромке окна: карта высот + осыпание.

Порт модели SettledSurface из Flake (macOS), переведённый на numpy.
Высота отсчитывается ВВЕРХ от верхней кромки окна.
"""
from __future__ import annotations

import numpy as np

CELL = 3.0
CORNER_WINDOW = 12.0
CORNER_TASKBAR = 2.0
MAX_SLOPE = 0.78
AVALANCHE_SLOPE = 0.72


class Surface:
    """Карта высот сугроба вдоль верхней кромки."""

    __slots__ = ("ledge_id", "x", "top", "width", "z", "is_taskbar",
                 "cell", "h", "_dist", "_corner_scale", "dirty",
                 "relax_enabled")

    def __init__(self, ledge_id: str, x: float, top: float, width: float,
                 z: int, is_taskbar: bool = False) -> None:
        self.ledge_id = ledge_id
        self.x = x
        self.top = top
        self.width = width
        self.z = z
        self.is_taskbar = is_taskbar
        self.cell = CELL
        self.dirty = True
        # Пока паровозик чистит полосу, снег не должен сползать обратно.
        self.relax_enabled = True
        count = max(4, int(np.ceil(width / CELL)))
        self.h = np.zeros(count, dtype=np.float32)
        self._rebuild_cache()

    # ------------------------------------------------------------------ #
    def _rebuild_cache(self) -> None:
        n = self.h.size
        lx = np.arange(n, dtype=np.float32) * self.cell
        dist = np.minimum(lx, np.maximum(0.0, self.width - lx))
        self._dist = dist
        corner = CORNER_TASKBAR if self.is_taskbar else CORNER_WINDOW
        if corner <= 0.5:
            self._corner_scale = np.ones(n, dtype=np.float32)
        else:
            self._corner_scale = np.where(
                dist < corner,
                np.maximum(0.15, dist / corner),
                1.0,
            ).astype(np.float32)

    def resize(self, x: float, top: float, width: float, z: int) -> None:
        self.x, self.top, self.z = x, top, z
        if abs(self.width - width) < 0.5:
            self.width = width
            return
        old = self.h
        count = max(4, int(np.ceil(width / CELL)))
        if old.size > 1 and count > 1:
            src = np.linspace(0, old.size - 1, count)
            i0 = np.floor(src).astype(np.int32)
            i1 = np.minimum(i0 + 1, old.size - 1)
            f = (src - i0).astype(np.float32)
            self.h = (old[i0] * (1 - f) + old[i1] * f).astype(np.float32)
        else:
            self.h = np.zeros(count, dtype=np.float32)
        self.width = width
        self._rebuild_cache()
        self.taper_edges()

    # ------------------------------------------------------------------ #
    @property
    def corner(self) -> float:
        return CORNER_TASKBAR if self.is_taskbar else CORNER_WINDOW

    @property
    def peak(self) -> float:
        return float(self.h.max()) if self.h.size else 0.0

    def height_at(self, local_x: float) -> float:
        if self.h.size == 0:
            return 0.0
        idx = local_x / self.cell
        i0 = int(np.floor(idx))
        i0 = max(0, min(self.h.size - 1, i0))
        i1 = min(self.h.size - 1, i0 + 1)
        f = idx - i0
        return float(self.h[i0] * (1 - f) + self.h[i1] * f)

    # ------------------------------------------------------------------ #
    def deposit_many(self, local_xs, amounts) -> None:
        """Пакетный слой снега от приземлившихся снежинок."""
        if self.h.size < 4 or len(local_xs) == 0:
            return
        lx = np.asarray(local_xs, dtype=np.float32)
        am = np.asarray(amounts, dtype=np.float32)
        keep = (lx >= 1.5) & (lx <= self.width - 1.5)
        if not keep.any():
            return
        lx = lx[keep]
        am = am[keep]
        n = self.h.size
        idx = np.rint(lx / self.cell).astype(np.int32)
        radius = 3 if self.is_taskbar else 2
        cap_limit = 1.35 if self.is_taskbar else 1.1
        dep = np.minimum(am, cap_limit)
        for d in range(-radius, radius + 1):
            i = idx + d
            valid = (i >= 0) & (i < n)
            if not valid.any():
                continue
            w = 1.0 - abs(d) / (radius + 1)
            np.add.at(self.h, i[valid], dep[valid] * w)
        cap = (18.0 if self.is_taskbar else 26.0) * self._corner_scale
        np.minimum(self.h, cap, out=self.h)
        self.relax(1)
        self.taper_edges()

    def add_snow(self, local_x: float, amount: float) -> None:
        self.deposit_many([local_x], [amount])

    # ------------------------------------------------------------------ #
    def relax(self, iterations: int = 1) -> None:
        if not self.relax_enabled:
            return
        h = self.h
        if h.size < 3:
            return
        for _ in range(iterations):
            diff = h[:-1] - h[1:]
            left = np.where(diff > MAX_SLOPE, (diff - MAX_SLOPE) * 0.55, 0.0)
            right = np.where(diff < -MAX_SLOPE, (-diff - MAX_SLOPE) * 0.55, 0.0)
            h[:-1] -= left
            h[1:] += left
            h[1:] -= right
            h[:-1] += right
        self.dirty = True

    def taper_edges(self) -> None:
        """Скругление на углах окна: снег не свисает за скруглённую рамку."""
        if self.h.size <= 4:
            self.h[:] = 0
            return
        r = self.corner
        if r <= 0.5:
            return
        mask = self._dist < r
        if not mask.any():
            return
        t = np.clip((self._dist - 0.75) / max(0.75, r - 0.75), 0.0, 1.0)
        scale = t * t * (3.0 - 2.0 * t)
        self.h[mask] *= scale[mask]
        self.relax(1)

    # ------------------------------------------------------------------ #
    def avalanche(self, iterations: int = 2, peel_corners: bool = True):
        """Сползание слишком крутых склонов. Возвращает массу, ушедшую за края."""
        if self.h.size < 3:
            return (0.0, 0.0)
        h = self.h
        spill_left = 0.0
        spill_right = 0.0
        for _ in range(iterations):
            diff = h[:-1] - h[1:]
            mask = diff > AVALANCHE_SLOPE
            if mask.any():
                move = np.minimum(h[:-1], (diff - AVALANCHE_SLOPE) * 0.65)
                move = np.where(mask, np.maximum(move, 0.0), 0.0)
                h[:-1] -= move
                h[1:] += move * 0.92
                if mask[-1]:
                    drip = move[-1] * 0.28
                    h[-1] = max(0.0, h[-1] - drip)
                    spill_right += float(drip)
            diff = h[:-1] - h[1:]
            mask = diff < -AVALANCHE_SLOPE
            if mask.any():
                move = np.minimum(h[1:], (-diff - AVALANCHE_SLOPE) * 0.65)
                move = np.where(mask, np.maximum(move, 0.0), 0.0)
                h[1:] -= move
                h[:-1] += move * 0.92
                if mask[0]:
                    drip = move[0] * 0.28
                    h[0] = max(0.0, h[0] - drip)
                    spill_left += float(drip)
            if not peel_corners:
                continue
            cells = max(1, int(np.ceil(self.corner / self.cell)))
            for i in range(min(cells, h.size)):
                peel = h[i] * 0.06
                if peel > 0.04:
                    h[i] -= peel
                    spill_left += float(peel)
            for i in range(max(0, h.size - cells), h.size):
                peel = h[i] * 0.06
                if peel > 0.04:
                    h[i] -= peel
                    spill_right += float(peel)
        self.dirty = True
        return (spill_left, spill_right)

    def plow(self, local_x: float, delta_x: float, delta_y: float):
        """Палец в снегу: разгребает под курсором и сгребает в валики."""
        h = self.h
        if h.size < 6:
            return (0.0, 0.0)
        travel = (delta_x * delta_x + delta_y * delta_y) ** 0.5
        if travel <= 0.15:
            return (0.0, 0.0)

        center = int(round(local_x / self.cell))
        brush = max(3, min(9, int(3.5 + travel * 0.9)))
        dig = min(4.0, 0.7 + travel * 1.15 + max(0.0, -delta_y) * 0.45)
        direction = 0
        if abs(delta_x) >= 0.2:
            direction = 1 if delta_x > 0 else -1
        ahead = max(1, min(7, int(1.5 + abs(delta_x) * 0.65)))
        rim = max(1, int(np.ceil(max(2.0, self.corner * 0.35) / self.cell)))

        spill_left = 0.0
        spill_right = 0.0
        n = h.size

        def bank(amount: float, dest: int) -> None:
            nonlocal spill_left, spill_right
            if amount <= 0.001:
                return
            if dest < 0:
                spill_left += amount
                return
            if dest >= n:
                spill_right += amount
                return
            if dest < rim:
                keep = min(n - 1, rim)
                drip = amount * 0.12
                h[keep] = min(32.0, float(h[keep]) + amount - drip)
                spill_left += drip
            elif dest >= n - rim:
                keep = max(0, n - 1 - rim)
                drip = amount * 0.12
                h[keep] = min(32.0, float(h[keep]) + amount - drip)
                spill_right += drip
            else:
                h[dest] = min(32.0, float(h[dest]) + amount)

        for d in range(-brush, brush + 1):
            i = center + d
            if i < 0 or i >= n:
                continue
            falloff = 1.0 - abs(d) / (brush + 1.0)
            soft = falloff * falloff
            take = min(float(h[i]), dig * soft * 1.35)
            if take <= 0.015:
                continue
            h[i] -= take
            if direction != 0:
                bank(take * 0.58, i + direction * ahead)
                bank(take * 0.22, i + direction * (ahead + 1))
                bank(take * 0.12, i + 1)
                bank(take * 0.08, i - 1)
            else:
                bank(take * 0.5, i + max(1, brush // 2))
                bank(take * 0.5, i - max(1, brush // 2))
        self.relax(2)
        self.dirty = True
        return (spill_left, spill_right)

    def scoop(self, local_x: float, radius: float) -> float:
        h = self.h
        if h.size == 0:
            return 0.0
        center = int(round(local_x / self.cell))
        cells = int(np.ceil(radius / self.cell))
        taken = 0.0
        for d in range(-cells, cells + 1):
            i = center + d
            if i < 0 or i >= h.size:
                continue
            falloff = 1.0 - abs(d) / (cells + 1.0)
            amount = min(float(h[i]), 0.95 * falloff * falloff)
            h[i] -= amount
            taken += amount
        self.relax(1)
        self.dirty = True
        return taken

    def scrape(self, left_local: float, right_local: float, fraction: float):
        h = self.h
        if h.size == 0 or right_local <= left_local:
            return (0.0, 0.0)
        lo = max(0, int(np.floor(left_local / self.cell)))
        hi = min(h.size - 1, int(np.ceil(right_local / self.cell)))
        if lo > hi:
            return (0.0, 0.0)
        keep = max(0.0, min(1.0, 1.0 - fraction))
        band = h[lo:hi + 1]
        peak = float(band.max())
        taken = float(band.sum()) * (1.0 - keep)
        h[lo:hi + 1] = band * keep
        if taken > 0.01:
            self.taper_edges()
        self.dirty = True
        return (taken, peak)

    def max_height_band(self, left_local: float, right_local: float) -> float:
        h = self.h
        if h.size == 0 or right_local <= left_local:
            return 0.0
        lo = max(0, int(np.floor(left_local / self.cell)))
        hi = min(h.size - 1, int(np.ceil(right_local / self.cell)))
        if lo > hi:
            return 0.0
        return float(h[lo:hi + 1].max())

    # ------------------------------------------------------------------ #
    def restore_mound(self, local_x: float, peak: float = 11.0, radius: float = 28.0) -> None:
        h = self.h
        if h.size == 0:
            return
        corner = self.corner
        clamped = max(corner + 1, min(self.width - corner - 1, local_x))
        center = int(round(clamped / self.cell))
        cells = max(2, int(np.ceil(radius / self.cell)))
        for d in range(-cells, cells + 1):
            i = center + d
            if i < 0 or i >= h.size:
                continue
            lx = i * self.cell
            if lx < corner or lx > self.width - corner:
                continue
            t = 1.0 - abs(d) / (cells + 1.0)
            target = peak * t * t
            h[i] = min(26.0, max(float(h[i]), target))
        self.relax(2)
        self.taper_edges()
        self.dirty = True

    def deposit_collapse_pile(self, local_x: float, add_peak: float, radius: float) -> None:
        h = self.h
        if h.size == 0 or add_peak <= 0.5:
            return
        corner = self.corner
        clamped = max(corner + 1, min(self.width - corner - 1, local_x))
        center = int(round(clamped / self.cell))
        cells = max(3, int(np.ceil(radius / self.cell)))
        hard_cap = 36.0 if self.is_taskbar else 52.0
        for d in range(-cells, cells + 1):
            i = center + d
            if i < 0 or i >= h.size:
                continue
            lx = i * self.cell
            if lx < corner or lx > self.width - corner:
                continue
            t = 1.0 - abs(d) / (cells + 1.0)
            h[i] = min(hard_cap, float(h[i]) + add_peak * t * t)
        self.relax(1)
        self.taper_edges()
        self.dirty = True

    # ------------------------------------------------------------------ #
    def clear_range(self, left_local: float, right_local: float,
                    fraction: float = 0.92) -> float:
        """Счистить снег в полосе (без сползания). Возвращает снятый объём."""
        h = self.h
        if h.size == 0:
            return 0.0
        lo = max(0, int(left_local / self.cell))
        hi = min(h.size - 1, int(right_local / self.cell))
        if hi < lo:
            return 0.0
        band = h[lo:hi + 1]
        taken = float(band.sum()) * fraction
        band *= (1.0 - fraction)
        band[band < 0.05] = 0.0
        self.dirty = True
        return taken

    def melt(self, dt: float, rate: float = 26.0) -> None:
        """Постепенное таяние (пункты меню «Растаять»)."""
        if self.h.size == 0:
            return
        self.h *= max(0.0, 1.0 - rate * dt)
        self.h[self.h < 0.02] = 0.0
        self.dirty = True

    def is_empty(self) -> bool:
        return bool(self.h.size == 0 or self.h.max(initial=0.0) < 0.25)

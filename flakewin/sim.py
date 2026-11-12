"""Физика Flake для Windows: снежинки, сугробы, снежки, снеговики."""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

import numpy as np
from PySide6.QtCore import QRectF

from .drifts import Surface
from .tracker import Occluder, Snapshot, WindowTracker
from .train import TrainRunner
from .world import World

GRAVITY = 1500.0
BALL_MAX_MASS = 4000.0
BALL_VISUAL_MAX_RADIUS = 420.0
MAX_BALLS = 24
BALL_SPAWN_THRESHOLD = 11.0
# Больше четырёх снеговиков на столе — уже нашествие.
MAX_SNOWMEN = 4
# Сколько живёт снежок, брошенный снеговиком (потом тает).
THROWN_BALL_TTL = 9.0


# --------------------------------------------------------------------------- #
#  Снежок
# --------------------------------------------------------------------------- #

@dataclass(eq=False)
class Snowball:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    mass: float = 14.0
    held: bool = False
    stacked_on: "Snowball | None" = None
    resting: str | None = None
    spun: float = 0.0
    # Снежок, брошенный снеговиком: не годится как строительный материал и тает.
    from_snowman: bool = False
    ttl: float = 0.0

    @property
    def radius(self) -> float:
        m = max(self.mass, 1.0)
        small = min(28.0, 5.0 + math.sqrt(m) * 1.55)
        if m > 220.0:
            t = min(1.0, (m - 220.0) / (BALL_MAX_MASS - 220.0))
            giant = (t ** 0.9) * (BALL_VISUAL_MAX_RADIUS - 28.0)
        else:
            giant = 0.0
        return max(6.0, min(BALL_VISUAL_MAX_RADIUS, small + giant))


# --------------------------------------------------------------------------- #
#  Снеговик
# --------------------------------------------------------------------------- #

@dataclass(eq=False)
class Snowman:
    x: float
    y: float
    base_mass: float
    mid_mass: float
    head_mass: float
    held: bool = False
    resting: str | None = None
    sign_text: str = ""
    perform_t: float = 0.0
    perform_cd: float = 0.0
    throw_side: float = -1.0
    throw_released: bool = False
    was_near: bool = False
    idle_throw_cd: float = 0.0
    idle_throw: bool = False

    PERFORM_DURATION = 1.35
    STACK_END = 0.60
    HOP_END = 0.48
    # Общий масштаб фигурки: на экране 1080p снеговик должен читаться.
    SCALE = 1.55

    @property
    def base_r(self) -> float:
        return max(13.0, min(26.0, 6.5 + math.sqrt(self.base_mass) * 1.35)) * self.SCALE

    @property
    def mid_r(self) -> float:
        return max(10.0, min(19.0, 5.2 + math.sqrt(self.mid_mass) * 1.1)) * self.SCALE

    @property
    def head_r(self) -> float:
        return max(7.5, min(13.5, 4.8 + math.sqrt(self.head_mass) * 0.95)) * self.SCALE

    @property
    def mid_y(self) -> float:
        return self.y - (self.base_r + self.mid_r) * 0.68

    @property
    def head_y(self) -> float:
        return self.mid_y - (self.mid_r + self.head_r) * 0.68

    @property
    def top_y(self) -> float:
        return self.head_y - self.head_r

    @property
    def throw_t(self) -> float:
        if self.perform_t <= Snowman.STACK_END:
            return 0.0
        return min(1.0, (self.perform_t - Snowman.STACK_END) / (1.0 - Snowman.STACK_END))

    def ball_offset(self, index: int) -> float:
        """Вертикальное смещение шара (вниз положительное)."""
        t = self.perform_t
        if t <= 0.0:
            return 0.0
        if t < Snowman.HOP_END:
            start = index * 0.11
            dur = 0.24
            local = t - start
            if local <= 0.0 or local >= dur:
                return 0.0
            u = local / dur
            amp = (9.0, 14.0, 20.0)[index]
            return -math.sin(u * math.pi) * amp
        if t < Snowman.STACK_END:
            u = (t - Snowman.HOP_END) / (Snowman.STACK_END - Snowman.HOP_END)
            squash = math.sin(u * math.pi) * -2.0
            return -squash * (1.0, 0.7, 0.45)[index]
        tw = self.throw_t
        if tw < 0.42:
            u = tw / 0.42
            return math.sin(u * math.pi) * 2.4 * (1.0, 0.75, 0.5)[index]
        if tw < 0.58:
            u = (tw - 0.42) / 0.16
            return -math.sin(u * math.pi) * (4.0 + index * 1.2)
        return 0.0

    @property
    def pose_base(self):
        return (self.x, self.y + self.ball_offset(0))

    @property
    def pose_mid(self):
        bx, by = self.pose_base
        return (bx, by - (self.base_r + self.mid_r) * 0.68 + self.ball_offset(1))

    @property
    def pose_head(self):
        mx, my = self.pose_mid
        return (mx, my - (self.mid_r + self.head_r) * 0.68 + self.ball_offset(2))

    def arm_angle(self, left: bool) -> float:
        idle = 0.31
        side = -1.0 if left else 1.0
        if self.throw_t <= 0.0 or self.throw_side != side:
            return idle
        t = self.throw_t
        if t < 0.40:
            u = t / 0.40
            s = u * u * (3 - 2 * u)
            return idle + (1.15 - idle) * s
        if t < 0.55:
            u = (t - 0.40) / 0.15
            s = u * u * (3 - 2 * u)
            return 1.15 + (-0.4 - 1.15) * s
        u = min(1.0, (t - 0.55) / 0.45)
        s = u * u * (3 - 2 * u)
        return -0.4 + (idle + 0.4) * s

    def arm_shoulder(self, left: bool):
        d = -1.0 if left else 1.0
        mx, my = self.pose_mid
        return (mx + d * self.mid_r * 0.82, my + self.mid_r * 0.18)

    def arm_tip(self, left: bool):
        d = -1.0 if left else 1.0
        sx, sy = self.arm_shoulder(left)
        length = self.mid_r * 1.35
        angle = self.arm_angle(left)
        return (sx + d * math.cos(angle) * length, sy - math.sin(angle) * length)

    @property
    def sign_anchor(self):
        tx, ty = self.arm_tip(False)
        return (tx + self.mid_r * 0.12, ty - self.mid_r * 0.22)


# --------------------------------------------------------------------------- #
#  Поле снежинок (numpy)
# --------------------------------------------------------------------------- #

class FlakeField:
    def __init__(self) -> None:
        self.x = np.zeros(0, dtype=np.float64)
        self.y = np.zeros(0, dtype=np.float64)
        self.vx = np.zeros(0, dtype=np.float64)
        self.vy = np.zeros(0, dtype=np.float64)
        self.size = np.zeros(0, dtype=np.float64)
        self.opacity = np.zeros(0, dtype=np.float64)
        self.wobble = np.zeros(0, dtype=np.float64)
        self.phase = np.zeros(0, dtype=np.float64)

    @property
    def count(self) -> int:
        return int(self.x.size)

    # ------------------------------------------------------------------ #
    def spawn(self, xs, ys, intensity: float, wind: float) -> None:
        n = len(xs)
        if n == 0:
            return
        u = np.random.random(n)
        size = 1.15 + np.power(u, 2.15) * 4.6
        mass = np.maximum(0.35, size / 3.4)

        self.x = np.concatenate([self.x, np.asarray(xs, dtype=np.float64)])
        self.y = np.concatenate([self.y, np.asarray(ys, dtype=np.float64)])
        self.vx = np.concatenate([
            self.vx,
            wind * (0.2 + 0.25 / mass) + np.random.uniform(-16, 16, n),
        ])
        self.vy = np.concatenate([
            self.vy,
            (32 + mass * 48) * np.random.uniform(0.82, 1.18, n)
            * (0.78 + 0.32 * intensity),
        ])
        self.size = np.concatenate([self.size, size])
        self.opacity = np.concatenate([
            self.opacity,
            np.minimum(0.98, np.random.uniform(0.42, 0.78, n)
                       + (1.15 - np.minimum(1.15, mass)) * 0.18),
        ])
        self.wobble = np.concatenate([
            self.wobble,
            np.random.uniform(0.65, 2.15, n) / np.sqrt(mass),
        ])
        self.phase = np.concatenate([
            self.phase, np.random.uniform(0, 2 * math.pi, n)
        ])

    def compact(self, keep: np.ndarray) -> None:
        self.x = self.x[keep]
        self.y = self.y[keep]
        self.vx = self.vx[keep]
        self.vy = self.vy[keep]
        self.size = self.size[keep]
        self.opacity = self.opacity[keep]
        self.wobble = self.wobble[keep]
        self.phase = self.phase[keep]

    def clear(self) -> None:
        self.compact(np.zeros(0, dtype=bool))


# --------------------------------------------------------------------------- #
#  Симулятор
# --------------------------------------------------------------------------- #

@dataclass
class Outbound:
    x: float
    y: float
    vx: float
    vy: float
    mass: float


class Simulator:
    def __init__(self, world: World, tracker: WindowTracker, settings) -> None:
        self.world = world
        self.tracker = tracker
        self.settings = settings

        self.field = FlakeField()
        self.surfaces: dict[str, Surface] = {}
        self._missing: dict[str, float] = {}
        self.balls: list[Snowball] = []
        self.snowmen: list[Snowman] = []
        self.train_runner = TrainRunner()
        self.snapshot: Snapshot = Snapshot()

        self.intensity = float(settings["intensity"])
        self.mouse_enabled = bool(settings["mouse_enabled"])
        self.paused = bool(settings["paused"])

        self.mouse_x = -10000.0
        self.mouse_y = -10000.0
        self.mouse_vx = 0.0
        self.mouse_vy = 0.0
        self.mouse_down = False
        self.right_down = False
        self._was_down = False
        self._was_right = False

        self.wind = 0.0
        self.wind_target = 0.0
        self.wind_timer = 0.0
        self._spawn_acc: dict[int, float] = {}

        self.held_ball: int | None = None
        self.rolling_ball: int | None = None
        self.held_snowman: Snowman | None = None
        self.forming_mass = 0.0
        self.flick_vx = 0.0
        self.flick_vy = 0.0
        self._flick_still = 0.0

        self.melting = 0.0
        self.outbound: list[Outbound] = []
        self.on_sign_request = None       # callable(Snowman)
        self.on_toast = None              # callable(str)
        self._last_settle = 0.0
        self._prev_occluders: list[Occluder] = []
        self._prev_poses: dict[str, tuple] = {}

    # ------------------------------------------------------------------ #
    #  Главный шаг
    # ------------------------------------------------------------------ #
    def update(self, dt: float, active: bool = False) -> None:
        dt = min(max(dt, 0.0), 1.0 / 20.0)
        if dt <= 0.0:
            return

        self.snapshot = self.tracker.snapshot(active=active)
        self._sync_surfaces()

        if self.paused:
            self._update_balls(dt)
            return

        self._update_wind(dt)
        self._spawn(dt)
        self._integrate(dt)
        if self.mouse_enabled:
            self._handle_mouse(dt)
        else:
            self.held_ball = None
            self.rolling_ball = None
        self._update_balls(dt)
        self._update_snowmen(dt)
        self.train_runner.update(dt, self)
        self._settle_drifts()
        self._apply_melt(dt)
        self._was_down = self.mouse_down
        self._was_right = self.right_down

    # ------------------------------------------------------------------ #
    #  Сугробы: синхронизация с окнами
    # ------------------------------------------------------------------ #
    def _sync_surfaces(self) -> None:
        now = time.perf_counter()
        seen: set[str] = set()
        for ledge in self.snapshot.ledges:
            if not ledge.can_accumulate:
                continue
            seen.add(ledge.id)
            self._missing.pop(ledge.id, None)
            surface = self.surfaces.get(ledge.id)
            if surface is None:
                self.surfaces[ledge.id] = Surface(
                    ledge.id, ledge.x, ledge.top, ledge.width, ledge.z,
                    is_taskbar=ledge.is_taskbar,
                )
            else:
                surface.resize(ledge.x, ledge.top, ledge.width, ledge.z)

        for lid in list(self.surfaces.keys()):
            if lid in seen:
                continue
            since = self._missing.setdefault(lid, now)
            if now - since > 8.0:
                self.surfaces.pop(lid, None)
                self._missing.pop(lid, None)

    def active_surface_ids(self) -> set[str]:
        return {lg.id for lg in self.snapshot.ledges if lg.can_accumulate}

    # ------------------------------------------------------------------ #
    def _update_wind(self, dt: float) -> None:
        self.wind_timer -= dt
        if self.wind_timer <= 0:
            nxt = random.uniform(-22, 22)
            if random.random() < 0.18:
                nxt *= random.uniform(1.5, 2.2)
            self.wind_target = nxt
            self.wind_timer = random.uniform(1.6, 5.5)
        self.wind += (self.wind_target - self.wind) * min(1.0, dt * 0.55)

    # ------------------------------------------------------------------ #
    def _spawn(self, dt: float) -> None:
        screens = self.world.screens
        if not screens:
            return
        cap = min(2200, int(1200 * len(screens) * max(1.0, self.intensity)))
        blocked = self.snapshot.blocked
        per_point = 0.07 * self.intensity

        for screen in screens:
            rect = screen.logical
            acc = self._spawn_acc.get(screen.index, 0.0)
            acc += max(22.0, per_point * rect.width()) * dt
            room = cap - self.field.count
            if room <= 0:
                self._spawn_acc[screen.index] = min(acc, 8.0)
                continue
            n = int(min(acc, room, 90))
            if n <= 0:
                self._spawn_acc[screen.index] = acc
                continue
            acc -= n
            self._spawn_acc[screen.index] = acc

            xs = np.random.uniform(rect.left(), rect.right(), n)
            ys = rect.top() - np.random.uniform(4.0, 56.0, n)
            if blocked:
                keep = np.ones(n, dtype=bool)
                for area in blocked:
                    inside = ((xs >= area.left()) & (xs <= area.right())
                              & (ys >= area.top() - 20) & (ys <= area.bottom()))
                    keep &= ~inside
                if not keep.all():
                    if not keep.any():
                        continue
                    xs = xs[keep]
                    ys = ys[keep]
            self.field.spawn(xs, ys, self.intensity, self.wind)

    # ------------------------------------------------------------------ #
    def _integrate(self, dt: float) -> None:
        f = self.field
        if f.count == 0:
            return

        mass = np.clip(f.size / 3.4, 0.35, 1.7)
        flutter = np.maximum(0.35, f.wobble)

        f.phase += dt * (1.5 + flutter * 1.7 + (2.0 - mass) * 0.6)
        terminal = 26.0 + mass * 58.0
        f.vy += (terminal - f.vy) * dt * (0.28 + 0.22 * mass)
        wind_catch = 0.1 + 0.28 / mass
        f.vx += (self.wind * (0.65 + 0.55 / mass) - f.vx) * dt * wind_catch
        sway = (np.sin(f.phase) * 12.0 * flutter
                + np.sin(f.phase * 2.31 + 0.7) * 5.5 * flutter)
        bob = np.cos(f.phase * 1.63) * (4.2 * flutter / mass)
        f.x += (f.vx + sway) * dt
        f.y += (f.vy + bob) * dt

        alive = np.ones(f.count, dtype=bool)
        bounds = self.world.bounds()

        # Вышли за пределы рабочего стола.
        alive &= ~((f.y < bounds.top() - 220)
                   | (f.x < bounds.left() - 200)
                   | (f.x > bounds.right() + 200))

        # Экран, закрытый развёрнутым окном — снежинки там не рисуются.
        for area in self.snapshot.blocked:
            inside = ((f.x >= area.left()) & (f.x <= area.right())
                      & (f.y >= area.top()) & (f.y <= area.bottom()))
            alive &= ~inside

        self._settle_on_ledges(alive, dt)
        self._bounce_windows(alive)
        f.compact(alive)

    # ------------------------------------------------------------------ #
    def _settle_on_ledges(self, alive: np.ndarray, dt: float) -> None:
        f = self.field
        ledges = [lg for lg in self.snapshot.ledges if lg.can_accumulate]
        if not ledges:
            return
        ledges.sort(key=lambda lg: lg.top)

        deposits: dict[str, tuple[list[float], list[float]]] = {}

        for ledge in ledges:
            surface = self.surfaces.get(ledge.id)
            if surface is None or surface.h.size == 0:
                continue
            idx = np.nonzero(
                alive
                & (f.x >= ledge.x - 1.0)
                & (f.x <= ledge.x + ledge.width + 1.0)
                & (f.y >= ledge.top - 40.0)
                & (f.y <= ledge.top + 4.0)
            )[0]
            if idx.size == 0:
                continue

            local = np.clip(f.x[idx] - ledge.x, 0.0, ledge.width)
            cell_idx = local / surface.cell
            i0 = np.floor(cell_idx).astype(np.int32)
            np.clip(i0, 0, surface.h.size - 1, out=i0)
            i1 = np.minimum(i0 + 1, surface.h.size - 1)
            frac = cell_idx - i0
            pile = surface.h[i0] * (1 - frac) + surface.h[i1] * frac

            ground = ledge.top - pile
            band = np.maximum(3.5, 2.0 + pile * 0.08)
            hit = (f.y[idx] >= ground - band) & (f.y[idx] <= ledge.top + 2.5)

            if not hit.any():
                continue
            for flake in idx[hit]:
                if not self._is_topmost(ledge, float(f.x[flake])):
                    continue
                bucket = deposits.setdefault(ledge.id, ([], []))
                bucket[0].append(float(f.x[flake] - ledge.x))
                bucket[1].append(0.55 + float(f.size[flake]) * 0.22)
                alive[flake] = False

        for lid, (xs, am) in deposits.items():
            surface = self.surfaces.get(lid)
            if surface is not None:
                surface.deposit_many(xs, am)

    def _is_topmost(self, ledge, x: float) -> bool:
        for other in self.snapshot.ledges:
            if other.id == ledge.id:
                continue
            if (other.z < ledge.z
                    and other.x <= x <= other.x + other.width
                    and ledge.top - 1 <= other.top <= ledge.top + 28):
                return False
        return True

    # ------------------------------------------------------------------ #
    def _bounce_windows(self, alive: np.ndarray) -> None:
        f = self.field
        if f.count == 0:
            return
        for occ in self.snapshot.occluders:
            if occ.is_taskbar:
                continue
            inside = (alive
                      & (f.x >= occ.x) & (f.x <= occ.right)
                      & (f.y >= occ.top + 2.0) & (f.y <= occ.bottom))
            if not inside.any():
                continue
            idx = np.nonzero(inside)[0]
            for i in idx:
                x = float(f.x[i])
                y = float(f.y[i])
                push = float(f.size[i]) + 9.0
                left_gap = x - occ.x
                right_gap = occ.right - x
                if left_gap < right_gap:
                    f.x[i] = occ.x - push
                    f.vx[i] = -abs(float(f.vx[i])) * 0.4 - 38.0
                else:
                    f.x[i] = occ.right + push
                    f.vx[i] = abs(float(f.vx[i])) * 0.4 + 38.0
                if y > occ.bottom - 6.0:
                    f.y[i] = occ.bottom + push
                    f.vy[i] = max(20.0, float(f.vy[i]))

    # ------------------------------------------------------------------ #
    #  Мышь
    # ------------------------------------------------------------------ #
    def _handle_mouse(self, dt: float) -> None:
        self._wake_flakes(dt)
        if self.held_snowman is None:
            self._plow_or_scoop(dt)

        if self.mouse_down and not self._was_down:
            self._grab()
        if not self.mouse_down and self._was_down:
            self._release()
        if self.right_down and not self._was_right:
            self._right_click()

    def _wake_flakes(self, dt: float) -> None:
        f = self.field
        if f.count == 0:
            return
        speed = math.hypot(self.mouse_vx, self.mouse_vy)
        dx = f.x - self.mouse_x
        dy = f.y - self.mouse_y
        d2 = dx * dx + dy * dy
        radius = 92.0
        near = d2 < radius * radius
        if not near.any():
            return
        d = np.sqrt(np.maximum(d2[near], 0.01))
        falloff = 1.0 - d / radius
        soft = falloff * falloff
        nx = dx[near] / d
        ny = dy[near] / d
        lightness = np.clip(3.6 / np.maximum(1.2, f.size[near]), 0.55, 1.45)
        wake = min(1.0, dt * 55.0)
        push = soft * (55.0 + min(280.0, speed * 0.85)) * lightness
        f.vx[near] += nx * push * wake
        f.vy[near] += ny * push * wake
        drag = soft * min(0.55, 0.12 + speed * 0.0011) * lightness
        f.vx[near] += self.mouse_vx * drag * wake
        f.vy[near] += self.mouse_vy * drag * wake

    def _plow_or_scoop(self, dt: float) -> None:
        speed = math.hypot(self.mouse_vx, self.mouse_vy)
        dt_safe = max(dt, 1.0 / 60.0)
        delta_x = self.mouse_vx * dt_safe
        delta_y = self.mouse_vy * dt_safe
        travel = math.hypot(delta_x, delta_y)
        brushed = False

        for lid, surface in list(self.surfaces.items()):
            if self.mouse_x < surface.x - 12 or self.mouse_x > surface.x + surface.width + 12:
                continue
            local = max(0.0, min(surface.width, self.mouse_x - surface.x))
            pile = surface.height_at(local)
            ground = surface.top - pile
            dy = self.mouse_y - ground
            if not (-12.0 < dy < 30.0) or pile <= 0.2:
                continue
            brushed = True

            if self.mouse_down:
                if speed > 5.0 and pile > 0.8:
                    scoop_radius = min(8.0, 3.8 + pile * 0.13)
                    scooped = surface.scoop(local, scoop_radius)
                    gained = scooped * 0.2
                    if gained > 0.03:
                        self._grow_or_spawn_ball(
                            gained, self.mouse_x,
                            max(self.mouse_y, ground + 8),
                            self.mouse_vx * 0.2, self.mouse_vy * 0.1,
                        )
            elif travel > 0.18:
                before = surface.height_at(local)
                spill_l, spill_r = surface.plow(local, delta_x, delta_y)
                after = surface.height_at(local)
                if abs(before - after) > 0.01 or spill_l + spill_r > 0.02:
                    surface.dirty = True
                if spill_l > 0.06:
                    self._spill_off(surface, spill_l, -1, max(30.0, speed))
                if spill_r > 0.06:
                    self._spill_off(surface, spill_r, 1, max(30.0, speed))

                edge_zone = 24.0
                toward_left = delta_x < -1.2 and local < edge_zone
                toward_right = delta_x > 1.2 and local > surface.width - edge_zone
                if travel > 2.5 and (toward_left or toward_right):
                    side = -1 if toward_left else 1
                    edge_local = 4.0 if side < 0 else surface.width - 4.0
                    scraped = surface.scoop(edge_local, 16.0)
                    if scraped > 0.12:
                        self._spill_off(surface, scraped * 0.7, side, max(55.0, speed))

        if self.mouse_down and not brushed and self.rolling_ball is None and self.held_ball is None:
            self.forming_mass = max(0.0, self.forming_mass - dt * 4.0)

    def _spill_off(self, surface: Surface, amount: float, side: int, speed: float) -> None:
        count = int(min(6, max(1, amount)))
        for _ in range(count):
            jitter = random.uniform(-14, 14)
            x = surface.x + (4.0 if side < 0 else surface.width - 4.0)
            self.field.spawn(
                [x], [surface.top - 2.0], self.intensity, self.wind * 0.2
            )
            i = self.field.count - 1
            if 0 <= i < self.field.count:
                self.field.vx[i] = side * (speed * 0.55 + jitter)
                self.field.vy[i] = -random.uniform(40, 120)

    # ------------------------------------------------------------------ #
    def _grab(self) -> None:
        # Снеговик в приоритете: его можно переставить, а не разобрать на снежок.
        man = self.snowman_at(self.mouse_x, self.mouse_y)
        if man is not None:
            man.held = True
            man.resting = None
            man.perform_t = 0.0
            man.throw_released = False
            man.idle_throw = False
            man.vy = 0.0
            self.held_snowman = man
            return

        best = None
        best_d = None
        for i, ball in enumerate(self.balls):
            d = math.hypot(ball.x - self.mouse_x, ball.y - self.mouse_y)
            if d < ball.radius + 26 and (best_d is None or d < best_d):
                best, best_d = i, d
        if best is not None:
            self.held_ball = best
            self.balls[best].held = True
            self.balls[best].stacked_on = None
            self.balls[best].resting = None
            return

        if self.forming_mass >= BALL_SPAWN_THRESHOLD:
            self._grow_or_spawn_ball(0.0, self.mouse_x, self.mouse_y, 0.0, 0.0)

    def _release(self) -> None:
        if self.held_snowman is not None:
            self._place_held_snowman()
            return

        idx = self.held_ball
        if idx is None and self.rolling_ball is not None:
            idx = self.rolling_ball
        if idx is None:
            self.forming_mass = 0.0
            return
        if not (0 <= idx < len(self.balls)):
            self.held_ball = None
            self.rolling_ball = None
            return
        ball = self.balls[idx]
        ball.held = False
        speed_bonus = math.hypot(self.flick_vx, self.flick_vy)
        ball.vx = self.flick_vx * 0.85 if speed_bonus > 40 else self.mouse_vx * 0.6
        ball.vy = self.flick_vy * 0.85 if speed_bonus > 40 else self.mouse_vy * 0.6
        ball.vy -= 90.0
        self.held_ball = None
        self.rolling_ball = None
        self.forming_mass = 0.0

    def _place_held_snowman(self) -> None:
        """Отпустили снеговика — ставим на кромку под ним, иначе пусть падает."""
        man = self.held_snowman
        self.held_snowman = None
        if man is None:
            return
        man.held = False
        foot = man.y + man.base_r * 0.75
        ledge = self._best_ledge_for(man.x, foot, max_dy=180.0)
        if ledge is not None:
            surface = self.surfaces.get(ledge.id)
            local = max(3.0, min(ledge.width - 3.0, man.x - ledge.x))
            pile = surface.height_at(local) if surface else 0.0
            man.x = ledge.x + local
            man.y = ledge.top - pile - man.base_r * 0.75
            man.resting = ledge.id
            man.vy = 0.0
            if surface is not None:
                surface.restore_mound(local, 11.0, 28.0)
        else:
            man.vy = 30.0
        man.perform_cd = 2.5
        man.was_near = True

    def _right_click(self) -> None:
        man = self.snowman_at(self.mouse_x, self.mouse_y)
        if man is not None and self.on_sign_request is not None:
            self.on_sign_request(man)

    # ------------------------------------------------------------------ #
    def _grow_or_spawn_ball(self, mass: float, x: float, y: float,
                            vx: float, vy: float) -> None:
        idx = self.held_ball if self.held_ball is not None else self.rolling_ball
        if idx is not None and 0 <= idx < len(self.balls):
            ball = self.balls[idx]
            ball.mass = min(BALL_MAX_MASS, ball.mass + mass)
            return
        self.forming_mass += mass
        if self.forming_mass < BALL_SPAWN_THRESHOLD and mass < BALL_SPAWN_THRESHOLD:
            return
        if len(self.balls) >= MAX_BALLS:
            return
        ball = Snowball(x, y, vx, vy, max(BALL_SPAWN_THRESHOLD, self.forming_mass))
        ball.held = self.mouse_down
        self.balls.append(ball)
        index = len(self.balls) - 1
        if self.mouse_down:
            self.held_ball = index
            self.rolling_ball = index
        self.forming_mass = 0.0

    # ------------------------------------------------------------------ #
    #  Снежки
    # ------------------------------------------------------------------ #
    def _update_balls(self, dt: float) -> None:
        if not self.balls:
            return
        bounds = self.world.bounds()
        remove: set[int] = set()

        for i, ball in enumerate(self.balls):
            if i in remove:
                continue

            # Брошенный снеговиком снежок живёт недолго и не идёт в постройку.
            if ball.ttl > 0.0:
                ball.ttl -= dt
                if ball.ttl <= 0.0:
                    remove.add(i)
                    continue

            if ball.held:
                ball.x = self.mouse_x
                ball.y = self.mouse_y
                ball.vx = 0.0
                ball.vy = 0.0
                ball.spun += math.hypot(self.mouse_vx, self.mouse_vy) * dt * 0.02
                continue

            if ball.stacked_on is not None:
                base = ball.stacked_on
                if base not in self.balls:
                    ball.stacked_on = None
                else:
                    ball.x = base.x
                    ball.y = base.y - base.radius - ball.radius * 0.92
                    ball.vx = 0.0
                    ball.vy = 0.0
                    continue

            ball.vy += GRAVITY * dt
            ball.vx *= max(0.0, 1.0 - 0.55 * dt)
            prev_y = ball.y
            ball.x += ball.vx * dt
            ball.y += ball.vy * dt
            ball.spun += math.hypot(ball.vx, ball.vy) * dt * 0.01

            # Попадание на уже лежащий снежок — ложимся сверху.
            if ball.vy > 0 and not ball.from_snowman:
                landed_on = None
                for other in self.balls:
                    if other is ball or other.held:
                        continue
                    if other.stacked_on is ball:
                        continue
                    if abs(other.x - ball.x) > other.radius * 0.8:
                        continue
                    if ball.y >= other.y:
                        continue
                    if ball.y + ball.radius >= other.y - other.radius:
                        landed_on = other
                        break
                if landed_on is not None:
                    ball.stacked_on = landed_on
                    ball.resting = landed_on.resting
                    ball.x = landed_on.x
                    ball.y = landed_on.y - landed_on.radius - ball.radius * 0.92
                    ball.vx = 0.0
                    ball.vy = 0.0
                    self._maybe_promote(ball)
                    continue

            # Отскок от окон.
            for occ in self.snapshot.occluders:
                if (ball.x + ball.radius < occ.x or ball.x - ball.radius > occ.right
                        or ball.y + ball.radius < occ.top + 2
                        or ball.y - ball.radius > occ.bottom):
                    continue
                left_gap = ball.x - occ.x
                right_gap = occ.right - ball.x
                if left_gap < right_gap:
                    ball.x = occ.x - ball.radius - 1
                    ball.vx = -abs(ball.vx) * 0.42
                else:
                    ball.x = occ.right + ball.radius + 1
                    ball.vx = abs(ball.vx) * 0.42
                ball.vy *= 0.86
                break

            # Приземление на кромку.
            settled = False
            for ledge in self.snapshot.ledges:
                if not (ledge.x - 2 <= ball.x <= ledge.x + ledge.width + 2):
                    continue
                surface = self.surfaces.get(ledge.id)
                pile = surface.height_at(ball.x - ledge.x) if surface else 0.0
                ground = ledge.top - pile
                if prev_y + ball.radius <= ground + 2 and ball.y + ball.radius >= ground:
                    if ball.vy > 0:
                        ball.y = ground - ball.radius
                        ball.vy = 0.0
                        ball.vx *= 0.5
                        ball.resting = ledge.id
                        settled = True
                        if abs(ball.vx) < 26:
                            ball.vx = 0.0
                        self._stack_ball(ball)
                        break
            if settled:
                continue

            # За край экрана — улетает другу (или тает).
            if ball.x < bounds.left() - 40 or ball.x > bounds.right() + 40:
                if abs(ball.vx) > 180:
                    direction = -1.0 if ball.x < bounds.left() else 1.0
                    self.outbound.append(Outbound(
                        bounds.left() if direction < 0 else bounds.right(),
                        ball.y, ball.vx, ball.vy, ball.mass,
                    ))
                remove.add(i)
                continue
            if ball.y > bounds.bottom() + 200:
                remove.add(i)

        if remove:
            self.balls = [b for i, b in enumerate(self.balls) if i not in remove]
            self.held_ball = None
            self.rolling_ball = None

    # ------------------------------------------------------------------ #
    #  Укладка снежков и рождение снеговика
    # ------------------------------------------------------------------ #
    def _stack_ball(self, ball: Snowball) -> None:
        """Снежок приземлился: положить его на снежок, который уже лежит рядом."""
        if ball.from_snowman:
            # Такие снежки только тают, снеговиков из них не лепим.
            return
        base = None
        best_dx = None
        for other in self.balls:
            if other is ball or other.held or other.resting != ball.resting:
                continue
            # Шар ниже (или на том же уровне) может стать опорой.
            if other.y < ball.y - 2.0:
                continue
            dx = abs(other.x - ball.x)
            if dx > other.radius * 0.95:
                continue
            if best_dx is None or dx < best_dx:
                base, best_dx = other, dx
        if base is not None:
            ball.stacked_on = base
            ball.x = base.x
            ball.y = base.y - base.radius - ball.radius * 0.92
            ball.vx = 0.0
            ball.vy = 0.0
            ball.resting = base.resting

            # Цепочку собираем от нижнего шара вверх.
            self._maybe_promote(ball)

    def _maybe_promote(self, ball: Snowball) -> None:
        root = ball
        guard = 0
        while root.stacked_on is not None and guard < 8:
            root = root.stacked_on
            guard += 1
        chain = self._stack_chain(root, limit=3)
        if len(chain) >= 3:
            self._promote_snowman(chain)

    def _stack_chain(self, ball: Snowball, limit: int = 3) -> list[Snowball]:
        chain = [ball]
        cur = ball
        guard = 0
        while guard < limit + 2:
            guard += 1
            nxt = None
            for other in self.balls:
                if other.stacked_on is cur:
                    nxt = other
                    break
            if nxt is None:
                break
            chain.append(nxt)
            cur = nxt
            if len(chain) >= limit:
                break
        return chain

    def _promote_snowman(self, chain: list[Snowball]) -> None:
        if len(self.snowmen) >= MAX_SNOWMEN:
            return
        masses = [b.mass for b in chain]
        bottom = chain[0]
        base_mass = max(masses) * 1.15
        mid_mass = sorted(masses)[len(masses) // 2] * 0.8
        head_mass = min(masses) * 0.6
        man = Snowman(bottom.x, bottom.y, base_mass, mid_mass, head_mass)
        man.resting = bottom.resting
        self.snowmen.append(man)
        self.balls = [b for b in self.balls if b not in chain]
        for b in self.balls:
            if b.stacked_on is not None and b.stacked_on in chain:
                b.stacked_on = None
        self.held_ball = None
        self.rolling_ball = None
        if self.on_toast:
            self.on_toast("Снеговик готов!")

    # ------------------------------------------------------------------ #
    #  Снеговики
    # ------------------------------------------------------------------ #
    def _ledge_by_id(self, lid: str):
        for ledge in self.snapshot.ledges:
            if ledge.id == lid:
                return ledge, self.surfaces.get(lid)
        return None, None

    def _best_ledge_for(self, x: float, y: float, max_dy: float = 260.0):
        """Кромка, на которую логично поставить снеговика рядом с точкой."""
        best = None
        best_score = None
        for ledge in self.snapshot.ledges:
            if not (ledge.x - 8 <= x <= ledge.x + ledge.width + 8):
                continue
            dy = abs(ledge.top - y)
            if dy > max_dy:
                continue
            # Предпочитаем кромку чуть ниже точки (ставим «на окно»).
            score = dy + (12.0 if ledge.top > y + 4 else 0.0)
            if best_score is None or score < best_score:
                best, best_score = ledge, score
        return best

    def place_snowman(self, x: float, y: float) -> Snowman | None:
        """Поставить снеговика на ближайшую кромку (None — если уже полно)."""
        if len(self.snowmen) >= MAX_SNOWMEN:
            return None
        man = Snowman(x, y, 90.0, 50.0, 26.0)
        ledge = self._best_ledge_for(x, y)

        # Фигурке нужно место сверху, иначе голова уйдёт за край экрана.
        need = (man.top_y - man.y) + 14.0
        top_limit = self.world.bounds().top()
        if ledge is not None and (ledge.top - top_limit) < need:
            lower = [lg for lg in self.snapshot.ledges
                     if lg.can_accumulate
                     and (lg.top - top_limit) >= need
                     and lg.x - 4 <= x <= lg.x + lg.width + 4]
            if lower:
                ledge = max(lower, key=lambda lg: lg.top)

        if ledge is not None:
            surface = self.surfaces.get(ledge.id)
            local = max(3.0, min(ledge.width - 3.0, x - ledge.x))
            pile = surface.height_at(local) if surface else 0.0
            man.x = ledge.x + local
            man.y = ledge.top - pile - man.base_r * 0.75
            man.vy = 0.0
            man.resting = ledge.id
            if surface is not None:
                surface.restore_mound(local, 13.0, max(28.0, man.base_r * 0.85))
        man.perform_cd = 3.0
        man.was_near = True
        man.idle_throw_cd = random.uniform(5.0, 10.0)
        self.snowmen.append(man)
        return man

    def snowman_at(self, x: float, y: float) -> Snowman | None:
        for man in self.snowmen:
            if (abs(man.x - x) < man.base_r * 1.6
                    and man.top_y - 12 < y < man.y + man.base_r):
                return man
        return None

    def _snowman_idle(self, man: Snowman, dt: float) -> None:
        """Реакция на наведение и собственные броски раз в несколько секунд."""
        d = math.hypot(self.mouse_x - man.x,
                       self.mouse_y - (man.mid_y - man.mid_r * 0.4))
        near = d < man.mid_r * 2.6
        if (near and not man.was_near and man.perform_cd <= 0.0
                and not self.mouse_down and self.mouse_enabled):
            man.perform_t = 0.0001
            man.throw_side = -1.0 if self.mouse_x < man.x else 1.0
            man.throw_released = False
            man.idle_throw = False
            man.perform_cd = 4.0
        man.was_near = near

        man.idle_throw_cd -= dt
        if man.idle_throw_cd <= 0.0 and man.perform_cd <= 0.0:
            man.idle_throw_cd = random.uniform(8.0, 18.0)
            man.perform_t = 0.0001
            man.throw_side = random.choice((-1.0, 1.0))
            man.throw_released = False
            man.idle_throw = True
            man.perform_cd = 3.0

    def _update_snowmen(self, dt: float) -> None:
        if not self.snowmen:
            return
        bounds = self.world.bounds()
        for man in list(self.snowmen):
            base_r = man.base_r

            if man.held:
                man.x = self.mouse_x
                man.y = self.mouse_y + base_r * 0.9
                man.vx = 0.0
                man.vy = 0.0
                continue

            man.perform_cd = max(0.0, man.perform_cd - dt)

            if man.perform_t > 0.0:
                man.perform_t += dt
                if not man.throw_released and man.throw_t > 0.45:
                    man.throw_released = True
                    self._snowman_throw(man, idle=man.idle_throw)
                if man.perform_t >= Snowman.PERFORM_DURATION:
                    man.perform_t = 0.0
                    man.throw_released = False
                    man.idle_throw = False
                    man.perform_cd = max(man.perform_cd, 2.2)
                    man.idle_throw_cd = random.uniform(8.0, 16.0)
                continue

            # Стоит на кромке — держим на сугробе.
            if man.resting is not None:
                ledge, surface = self._ledge_by_id(man.resting)
                if ledge is None:
                    man.resting = None
                else:
                    local = max(0.0, min(ledge.width, man.x - ledge.x))
                    pile = surface.height_at(local) if surface else 0.0
                    man.y = ledge.top - pile - base_r * 0.75
                    man.vy = 0.0
                    self._snowman_idle(man, dt)
                    continue

            # Падает: проверяем пересечение кромки с учётом шага за кадр.
            prev_y = man.y
            man.vy += GRAVITY * dt
            man.y += man.vy * dt
            landed = False
            for ledge in self.snapshot.ledges:
                if not (ledge.x - 4 <= man.x <= ledge.x + ledge.width + 4):
                    continue
                surface = self.surfaces.get(ledge.id)
                pile = surface.height_at(man.x - ledge.x) if surface else 0.0
                ground = ledge.top - pile
                if (prev_y + base_r * 0.75 <= ground + 1.5
                        and man.y + base_r * 0.75 >= ground):
                    man.y = ground - base_r * 0.75
                    man.vy = 0.0
                    man.resting = ledge.id
                    if surface is not None:
                        surface.restore_mound(man.x - ledge.x, 13.0,
                                              max(28.0, base_r * 0.85))
                    landed = True
                    break
            if landed:
                man.perform_cd = max(man.perform_cd, 1.0)
                continue

            # Улетел ниже экрана — возвращаем на панель задач, а не удаляем.
            if man.y > bounds.bottom() + 40:
                bar = next((lg for lg in self.snapshot.ledges if lg.is_taskbar), None)
                if bar is None:
                    self.snowmen.remove(man)
                    continue
                man.x = max(bar.x + 60.0, min(bar.x + bar.width - 60.0, man.x))
                surface = self.surfaces.get(bar.id)
                local = man.x - bar.x
                pile = surface.height_at(local) if surface else 0.0
                man.y = bar.top - pile - base_r * 0.75
                man.vy = 0.0
                man.resting = bar.id
                man.perform_cd = 2.0

    def _snowman_throw(self, man: Snowman, idle: bool = False) -> None:
        tx, ty = man.arm_tip(man.throw_side < 0)
        if idle:
            target_x = man.x + man.throw_side * random.uniform(240.0, 620.0)
            target_y = man.mid_y + random.uniform(-80.0, 30.0)
        else:
            target_x = self.mouse_x if self.mouse_x > -9000 else man.x + man.throw_side * 300
            target_y = self.mouse_y if self.mouse_y > -9000 else man.mid_y
        dx = target_x - tx
        dy = target_y - ty
        dist = max(1.0, math.hypot(dx, dy))
        speed = 900.0
        ball = Snowball(tx, ty, dx / dist * speed, dy / dist * speed - 160.0, 16.0)
        ball.from_snowman = True
        ball.ttl = THROWN_BALL_TTL
        if len(self.balls) < MAX_BALLS:
            self.balls.append(ball)

    # ------------------------------------------------------------------ #
    def _settle_drifts(self) -> None:
        now = time.perf_counter()
        if now - self._last_settle < 1.6:
            return
        self._last_settle = now
        for surface in self.surfaces.values():
            if surface.peak > 6.0:
                surface.avalanche(1, peel_corners=True)
                surface.relax(1)

    def _apply_melt(self, dt: float) -> None:
        if self.melting <= 0.0:
            return
        self.melting = max(0.0, self.melting - dt)
        for surface in self.surfaces.values():
            surface.melt(dt, 1.1)
        if self.melting <= 0.0:
            for surface in self.surfaces.values():
                surface.h[:] = 0.0
                surface.dirty = True

    # ------------------------------------------------------------------ #
    def clear(self, keep_balls: bool = False) -> None:
        self.field.clear()
        for surface in self.surfaces.values():
            surface.h[:] = 0.0
            surface.dirty = True
        self.balls.clear()
        self.snowmen.clear()
        self.held_ball = None
        self.rolling_ball = None
        self.held_snowman = None
        self.forming_mass = 0.0

    def melt(self) -> None:
        self.melting = 2.2

    def clear_snowmen(self) -> None:
        """Убрать всех снеговиков и их снежки."""
        self.snowmen.clear()
        self.held_snowman = None
        self.balls = [b for b in self.balls if not b.from_snowman]

    def snowman_count(self) -> int:
        return len(self.snowmen)

    # ------------------------------------------------------------------ #
    def set_intensity(self, value: float) -> None:
        self.intensity = max(0.25, min(1.4, float(value)))

    def has_blocked_screens(self) -> bool:
        return bool(self.snapshot.blocked)

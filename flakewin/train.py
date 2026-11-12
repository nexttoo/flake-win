"""Паровозик с отвалом: выезжает, когда на панели накопился снег,
проходит всю панель и счищает сугроб — снег осыпается вниз."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

# Средняя высота сугроба на панели, при которой выезжает паровозик.
SNOW_TRIGGER_MEAN = 3.2
# Чтобы не катался бесконечно по чистому — минимальная пауза между рейсами.
MIN_PAUSE = 30.0


@dataclass(eq=False)
class SmokePuff:
    x: float
    y: float
    life: float
    max_life: float
    size: float
    drift: float


@dataclass(eq=False)
class Train:
    x: float
    rail_y: float
    direction: int
    speed: float = 150.0
    wheel: float = 0.0
    smoke_timer: float = 0.0
    prev_x: float = 0.0
    puffs: list[SmokePuff] = field(default_factory=list)

    @property
    def length(self) -> float:
        return 116.0

    @property
    def height(self) -> float:
        return 52.0


class TrainRunner:
    """Рейсы по панели задач: по уровню снега или по команде из меню."""

    def __init__(self) -> None:
        self.train: Train | None = None
        self.enabled = True
        self.cooldown = 25.0
        self.forced = False
        self.last_taken = 0.0

    # ------------------------------------------------------------------ #
    def summon(self) -> None:
        """Позвать паровозик прямо сейчас."""
        self.forced = True
        self.cooldown = 0.0

    def level(self, sim) -> float:
        bar = next((lg for lg in sim.snapshot.ledges if lg.is_taskbar), None)
        if bar is None:
            return 0.0
        surface = sim.surfaces.get(bar.id)
        if surface is None or surface.h.size == 0:
            return 0.0
        return float(surface.h.mean())

    def update(self, dt: float, sim) -> None:
        bar = next((lg for lg in sim.snapshot.ledges if lg.is_taskbar), None)
        if bar is None or not self.enabled:
            self.train = None
            return

        surface = sim.surfaces.get(bar.id)

        if self.train is None:
            self.cooldown = max(0.0, self.cooldown - dt)
            if self.cooldown > 0.0:
                return
            snow = float(surface.h.mean()) if surface is not None and surface.h.size else 0.0
            if not self.forced and snow < SNOW_TRIGGER_MEAN:
                return
            self._start(bar)
            return

        self._advance(dt, sim, bar, surface)

    # ------------------------------------------------------------------ #
    def _start(self, bar) -> None:
        direction = random.choice((-1, 1))
        start_x = bar.x - 120.0 if direction > 0 else bar.x + bar.width + 120.0
        self.train = Train(x=start_x, rail_y=bar.top, direction=direction,
                           prev_x=start_x)
        self.forced = False

    def _finish(self, surface) -> None:
        self.train = None
        self.cooldown = MIN_PAUSE + random.uniform(0.0, 40.0)
        if surface is not None:
            # Доехал до края — панель остаётся чистой.
            surface.clear_range(0.0, surface.width, 0.92)
            surface.relax_enabled = True
            surface.h[surface.h < 0.05] = 0.0
            surface.relax(2)

    def _advance(self, dt: float, sim, bar, surface) -> None:
        train = self.train
        if train is None:
            return

        train.prev_x = train.x
        train.x += train.direction * train.speed * dt
        train.wheel += dt * 7.0

        # Дым из трубы.
        train.smoke_timer -= dt
        if train.smoke_timer <= 0.0:
            train.smoke_timer = 0.14
            train.puffs.append(SmokePuff(
                x=train.x - train.direction * 26.0,
                y=train.rail_y - 46.0,
                life=1.25,
                max_life=1.25,
                size=random.uniform(3.2, 6.4),
                drift=random.uniform(-16.0, 16.0) - train.direction * 10.0,
            ))
        for puff in train.puffs:
            puff.life -= dt
            puff.y -= 30.0 * dt
            puff.x += puff.drift * dt
            puff.size += 5.0 * dt
        train.puffs = [p for p in train.puffs if p.life > 0.0]

        # Отвал счищает полосу: пока едет, снег не сползает обратно.
        taken = 0.0
        if surface is not None and surface.h.size:
            surface.relax_enabled = False
            left = min(train.prev_x, train.x) - bar.x - 40.0
            right = max(train.prev_x, train.x) - bar.x + 40.0
            if right > 0 and left < bar.width:
                taken = surface.clear_range(left, right, 0.95)
            # Добираем по краям отвала, чтобы не оставалось гребня.
            edge = train.x - bar.x
            taken += surface.clear_range(edge - 46.0, edge + 46.0, 0.6)
        self.last_taken = taken

        if taken > 0.25:
            # Снег осыпается вниз с панели.
            for _ in range(min(7, 1 + int(taken / 6.0))):
                x = train.x + train.direction * random.uniform(-12.0, 34.0)
                y = bar.top - random.uniform(1.0, 9.0)
                sim.field.spawn([x], [y], sim.intensity, sim.wind * 0.2)
                index = sim.field.count - 1
                if 0 <= index < sim.field.count:
                    sim.field.vx[index] = train.direction * random.uniform(20.0, 90.0)
                    sim.field.vy[index] = random.uniform(60.0, 170.0)
                    sim.field.size[index] = random.uniform(1.8, 3.6)

        finished = (
            (train.direction > 0 and train.x > bar.x + bar.width + 140.0)
            or (train.direction < 0 and train.x < bar.x - 140.0)
        )
        if finished:
            self._finish(surface)

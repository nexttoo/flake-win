"""Паровозик с отвалом: катается по панели задач и расчищает снег."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


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
    speed: float = 118.0
    wheel: float = 0.0
    smoke_timer: float = 0.0
    plow_timer: float = 0.0
    puffs: list[SmokePuff] = field(default_factory=list)

    @property
    def length(self) -> float:
        return 108.0

    @property
    def height(self) -> float:
        return 52.0


class TrainRunner:
    """Появление, движение и расчистка полосы на панели задач."""

    def __init__(self) -> None:
        self.train: Train | None = None
        self.enabled = True
        self.cooldown = 28.0
        self.interval = (70.0, 150.0)

    # ------------------------------------------------------------------ #
    def summon(self) -> None:
        """Позвать паровозик прямо сейчас (пункт меню)."""
        if self.train is None:
            self.cooldown = 0.0

    def update(self, dt: float, sim) -> None:
        bar = next((lg for lg in sim.snapshot.ledges if lg.is_taskbar), None)
        if bar is None or not self.enabled:
            self.train = None
            return

        if self.train is None:
            self.cooldown -= dt
            if self.cooldown <= 0.0:
                self._start(bar)
            return

        self._advance(dt, sim, bar)

    # ------------------------------------------------------------------ #
    def _start(self, bar) -> None:
        direction = random.choice((-1, 1))
        start_x = bar.x - 110.0 if direction > 0 else bar.x + bar.width + 110.0
        self.train = Train(x=start_x, rail_y=bar.top, direction=direction)
        self.train.smoke_timer = 0.0

    def _advance(self, dt: float, sim, bar) -> None:
        train = self.train
        if train is None:
            return

        train.x += train.direction * train.speed * dt
        train.wheel += dt * 9.0

        # Дым из трубы.
        train.smoke_timer -= dt
        if train.smoke_timer <= 0.0:
            train.smoke_timer = 0.13
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

        # Отвал сгребает снег с панели задач.
        surface = sim.surfaces.get(bar.id)
        if surface is not None and surface.h.size:
            local = train.x - bar.x
            if 0.0 <= local <= bar.width:
                taken = surface.scoop(local, 26.0)
                if taken > 0.12:
                    count = min(4, 1 + int(taken))
                    for _ in range(count):
                        sim.field.spawn(
                            [train.x + train.direction * random.uniform(16.0, 44.0)],
                            [bar.top - random.uniform(0.0, 8.0)],
                            sim.intensity, sim.wind * 0.2,
                        )
                        index = sim.field.count - 1
                        if 0 <= index < sim.field.count:
                            sim.field.vx[index] = train.direction * random.uniform(70.0, 190.0)
                            sim.field.vy[index] = -random.uniform(70.0, 170.0)

        finished = (
            (train.direction > 0 and train.x > bar.x + bar.width + 130.0)
            or (train.direction < 0 and train.x < bar.x - 130.0)
        )
        if finished:
            self.train = None
            self.cooldown = random.uniform(*self.interval)

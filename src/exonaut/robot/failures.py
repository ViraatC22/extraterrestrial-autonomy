"""Unexpected in-mission faults.

These exist to test whether an autonomy stack degrades gracefully when its
own assumptions about *itself* stop holding, not just when the terrain
surprises it. Each fault is injected at a seeded time so that every algorithm
faces the identical fault at the identical step on the identical terrain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np


class FaultType(str, Enum):
    NONE = "none"
    SENSOR_DEGRADATION = "sensor_degradation"   # sensing range and accuracy drop
    MOTOR_EFFICIENCY = "motor_efficiency"       # locomotion costs more energy
    SOLAR_DUST = "solar_dust"                   # recharge rate drops
    WHEEL_DAMAGE = "wheel_damage"               # slip increases everywhere


@dataclass
class FaultEvent:
    fault_type: FaultType
    step: int
    severity: float  # in [0, 1]


@dataclass
class FaultSchedule:
    """A pre-drawn list of faults for one mission.

    Drawing the whole schedule up front from the trial seed (rather than
    sampling each step) guarantees that the faults are a property of the
    trial, identical across algorithms, and therefore a controlled variable
    rather than a source of between-algorithm noise.
    """
    events: list[FaultEvent] = field(default_factory=list)

    @classmethod
    def draw(cls, rng: np.random.Generator, horizon: int, fault_rate: float,
             allowed: tuple[FaultType, ...] = None) -> "FaultSchedule":
        if fault_rate <= 0:
            return cls([])
        allowed = allowed or (
            FaultType.SENSOR_DEGRADATION, FaultType.MOTOR_EFFICIENCY,
            FaultType.SOLAR_DUST, FaultType.WHEEL_DAMAGE,
        )
        # fault_rate is the expected number of faults per mission
        n_faults = rng.poisson(fault_rate)
        events = []
        for _ in range(int(n_faults)):
            events.append(FaultEvent(
                fault_type=FaultType(rng.choice([f.value for f in allowed])),
                step=int(rng.integers(1, max(2, horizon))),
                severity=float(rng.uniform(0.3, 0.9)),
            ))
        events.sort(key=lambda e: e.step)
        return cls(events)

    def due(self, step: int) -> list[FaultEvent]:
        return [e for e in self.events if e.step == step]

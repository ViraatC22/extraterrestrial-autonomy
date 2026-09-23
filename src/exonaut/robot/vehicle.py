"""The rover itself: mobility, slip, embedding, and fault response.

The central mechanic is **slip-driven immobilization**. A commanded move is
not guaranteed: the wheels turn, the ground gives way, and the robot advances
by less than commanded while still paying (more than) the full energy cost.
Sustained severe slip means the robot is digging in, and enough consecutive
severe-slip events end the mission permanently. This is the model's stand-in
for the way real planetary rovers are lost - embedding in soft ground rather
than driving off a cliff - and it is what gives "risk" a concrete, measurable
meaning in this study.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..environments.base import TerrainField
from .failures import FaultSchedule, FaultType
from .power import PowerSystem, locomotion_cost
from .sensors import SensorSuite

# A step is "severe slip" if this fraction of commanded motion is lost.
SEVERE_SLIP_THRESHOLD = 0.80
# Consecutive severe-slip steps before the robot is permanently embedded.
EMBED_LIMIT = 3


@dataclass
class SlipRecord:
    """One proprioceptive mobility measurement: what the robot felt when it
    actually drove on a cell. This is the high-quality evidence the world
    model learns from."""

    row: int
    col: int
    terrain_class: int
    slope: float
    slip: float
    energy: float


@dataclass
class Rover:
    row: int
    col: int
    max_slope_deg: float = 25.0
    power: PowerSystem = field(default_factory=PowerSystem)
    sensors: SensorSuite = field(default_factory=SensorSuite)
    motor_efficiency: float = 1.0
    slip_bias: float = 0.0  # added by wheel damage
    alive: bool = True
    immobilized: bool = False
    consecutive_severe_slip: int = 0
    path: list = field(default_factory=list)
    slip_history: list = field(default_factory=list)
    active_faults: list = field(default_factory=list)

    def __post_init__(self):
        if not self.path:
            self.path.append((self.row, self.col))

    @property
    def pos(self) -> tuple[int, int]:
        return (self.row, self.col)

    @property
    def operational(self) -> bool:
        return self.alive and not self.immobilized and not self.power.depleted

    # -- faults ------------------------------------------------------------
    def apply_faults(self, schedule: FaultSchedule, step: int) -> list:
        fired = schedule.due(step)
        for event in fired:
            if event.fault_type == FaultType.SENSOR_DEGRADATION:
                self.sensors.degradation = min(0.9, self.sensors.degradation + event.severity)
            elif event.fault_type == FaultType.MOTOR_EFFICIENCY:
                self.motor_efficiency = max(0.25, self.motor_efficiency - 0.5 * event.severity)
            elif event.fault_type == FaultType.SOLAR_DUST:
                self.power.solar_efficiency = max(
                    0.1, self.power.solar_efficiency - 0.6 * event.severity
                )
            elif event.fault_type == FaultType.WHEEL_DAMAGE:
                self.slip_bias = min(0.5, self.slip_bias + 0.25 * event.severity)
            self.active_faults.append(event)
        return fired

    # -- motion ------------------------------------------------------------
    def attempt_move(
        self, dr: int, dc: int, terrain: TerrainField, rng: np.random.Generator
    ) -> dict:
        """Try to drive one cell. Returns an outcome record.

        Outcome keys: moved, reason, slip, energy, record.
        """
        if not self.operational:
            return {
                "moved": False,
                "reason": "not_operational",
                "slip": 0.0,
                "energy": 0.0,
                "record": None,
            }

        target = (self.row + dr, self.col + dc)
        if not terrain.in_bounds(*target):
            return {"moved": False, "reason": "off_map", "slip": 0.0, "energy": 0.0, "record": None}

        # Onboard geometric hazard check: the robot refuses commands into
        # terrain it can see is lethal, regardless of what the planner asked.
        if terrain.hazard[target] or terrain.slope[target] > self.max_slope_deg:
            return {
                "moved": False,
                "reason": "hazard_refused",
                "slip": 0.0,
                "energy": 0.0,
                "record": None,
            }

        distance = float(np.hypot(dr, dc))
        mean, dispersion = terrain.true_slip_distribution(*target)
        mean = min(0.985, mean + self.slip_bias)
        slip = float(np.clip(rng.normal(mean, max(dispersion, 1e-6)), 0.0, 0.995))

        params = terrain.params_at(*target)
        energy = locomotion_cost(
            distance_cells=distance,
            slope_deg=float(terrain.slope[target]),
            energy_multiplier=params.energy_multiplier,
            slip=slip,
            gravity=terrain.gravity,
        ) / max(self.motor_efficiency, 1e-6)

        if not self.power.draw(energy):
            return {
                "moved": False,
                "reason": "insufficient_energy",
                "slip": slip,
                "energy": 0.0,
                "record": None,
            }

        record = SlipRecord(
            row=target[0],
            col=target[1],
            terrain_class=int(terrain.terrain_class[target]),
            slope=float(terrain.slope[target]),
            slip=slip,
            energy=energy,
        )
        self.slip_history.append(record)

        if slip >= SEVERE_SLIP_THRESHOLD:
            # Wheels turned, robot barely advanced: it is digging in.
            self.consecutive_severe_slip += 1
            if self.consecutive_severe_slip >= EMBED_LIMIT:
                self.immobilized = True
            return {
                "moved": False,
                "reason": "slip_no_progress",
                "slip": slip,
                "energy": energy,
                "record": record,
            }

        self.consecutive_severe_slip = 0
        self.row, self.col = target
        self.path.append(target)
        return {"moved": True, "reason": "ok", "slip": slip, "energy": energy, "record": record}

    def hold(self, illumination: float) -> None:
        """Stay put for one timestep: housekeeping draw, then recharge."""
        from .power import IDLE_DRAW_WH

        self.power.draw(min(IDLE_DRAW_WH, self.power.charge))
        self.power.recharge(illumination)

    def sense(self, terrain: TerrainField, rng: np.random.Generator) -> dict:
        from .power import SENSING_DRAW_WH

        self.power.draw(min(SENSING_DRAW_WH, self.power.charge))
        return self.sensors.observe(terrain, self.row, self.col, rng)

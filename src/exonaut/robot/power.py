"""Energy model.

Two quantities are tracked separately and must not be conflated:

  * `charge`   - what is in the battery right now.
  * `expended` - cumulative energy drawn over the mission.

They differ because the robot recharges from sunlight. Reporting the
end-of-mission battery deficit as "energy used" would silently subtract all
solar income and understate true expenditure, so `expended` is accumulated
explicitly at every draw.
"""
from __future__ import annotations

from dataclasses import dataclass

CAPACITY_WH = 100.0
IDLE_DRAW_WH = 0.08          # housekeeping per timestep
SENSING_DRAW_WH = 0.02       # per full sensor sweep
NOMINAL_SOLAR_WH = 0.55      # per timestep at full illumination
# Locomotion cost is normalized so that one axial cell on flat, ideal terrain
# at lunar gravity costs BASE_MOVE_WH.
BASE_MOVE_WH = 1.0
REFERENCE_GRAVITY = 1.62
SLOPE_ENERGY_COEFF = 0.035   # extra fraction of base cost per degree of slope


@dataclass
class PowerSystem:
    capacity: float = CAPACITY_WH
    charge: float = CAPACITY_WH
    expended: float = 0.0
    generated: float = 0.0
    solar_efficiency: float = 1.0   # degraded by dust-accumulation faults

    def draw(self, amount: float) -> bool:
        """Draw energy. Returns False (and draws nothing) if there is not
        enough charge, which is what makes the energy budget a hard
        constraint rather than an accounting note."""
        if amount <= 0:
            return True
        if self.charge < amount:
            return False
        self.charge -= amount
        self.expended += amount
        return True

    def recharge(self, illumination: float) -> float:
        gain = NOMINAL_SOLAR_WH * max(0.0, illumination) * self.solar_efficiency
        gain = min(gain, self.capacity - self.charge)
        self.charge += gain
        self.generated += gain
        return gain

    @property
    def fraction(self) -> float:
        return self.charge / self.capacity if self.capacity else 0.0

    @property
    def depleted(self) -> bool:
        return self.charge <= 0.0


def locomotion_cost(distance_cells: float, slope_deg: float, energy_multiplier: float,
                    slip: float, gravity: float) -> float:
    """Energy to cover `distance_cells` of ground.

    Slip appears in the denominator because slipping wheels still turn (and
    still consume power) while delivering less progress: at slip fraction s,
    covering the same ground costs roughly 1/(1-s) times as much. The
    denominator is floored so that near-total slip yields a large but finite
    cost rather than a singularity.
    """
    effective = max(1.0 - slip, 0.08)
    gravity_factor = gravity / REFERENCE_GRAVITY
    slope_factor = 1.0 + SLOPE_ENERGY_COEFF * max(0.0, slope_deg)
    return (BASE_MOVE_WH * distance_cells * energy_multiplier
            * slope_factor * gravity_factor / effective)

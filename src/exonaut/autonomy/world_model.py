"""The robot's belief about the world.

This is deliberately *not* the terrain. It is what the robot thinks the
terrain is, which is the only thing any planner in this project is allowed to
consult. It has two layers:

1. **Per-cell geometric belief** - slope, roughness, terrain-class guess and
   hazard probability, accumulated from noisy remote observations. Near
   observations overwrite far ones because sensor noise grows with range.

2. **Per-class mobility belief** - for each terrain class, a posterior over
   the mean slip fraction. This is the layer that matters scientifically.
   Geometry can be seen from a distance; *mobility* can only be measured by
   driving. So this belief starts from a prior calibrated elsewhere and can
   only be corrected by proprioceptive experience.

The mobility belief is a Normal-Normal conjugate model. With prior
mean m0 and variance t0^2, observation noise variance s^2, and n observed
slips with sample mean xbar:

    precision = 1/t0^2 + n/s^2
    posterior_mean = (m0/t0^2 + n*xbar/s^2) / precision
    posterior_var  = 1 / precision

Reporting `posterior_var` separately from `s^2` is the point: the first is
*epistemic* uncertainty (the robot does not know this terrain yet, and can
fix that by driving) while the second is *aleatoric* (the terrain is simply
variable, and driving more will not remove it). A planner that treats those
identically cannot tell "dangerous" apart from "unknown".
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..environments.base import N_TERRAIN_CLASSES, TerrainClass

# Assumed observation noise on a single slip measurement. Fixed and shared by
# every adaptive method so no method gains an advantage from a better-tuned
# noise model.
SLIP_OBS_VARIANCE = 0.02 ** 2


@dataclass
class ClassBelief:
    """Posterior over the mean slip fraction of one terrain class."""
    mean: float
    variance: float
    # The prior is retained so each update recomputes the posterior from the
    # prior and the full sample, rather than compounding successive updates -
    # which would make the result depend on update order.
    prior_mean: float = 0.0
    prior_variance: float = 0.01
    n_observations: int = 0
    observed_sum: float = 0.0

    def update(self, slip: float, obs_variance: float = SLIP_OBS_VARIANCE) -> None:
        """Conjugate update from one proprioceptive slip measurement."""
        self.n_observations += 1
        self.observed_sum += slip
        n = self.n_observations
        xbar = self.observed_sum / n
        precision = 1.0 / self.prior_variance + n / obs_variance
        self.mean = (self.prior_mean / self.prior_variance + n * xbar / obs_variance) / precision
        self.variance = 1.0 / precision

    @property
    def epistemic_sd(self) -> float:
        return float(np.sqrt(self.variance))


@dataclass
class CellBelief:
    slope: float = 0.0
    roughness: float = 0.0
    terrain_class: int = int(TerrainClass.SMOOTH_REGOLITH)
    hazard_prob: float = 0.0
    illumination: float = 0.5
    observed: bool = False
    best_range: float = np.inf


class WorldModel:
    """Belief state consulted by every planner."""

    def __init__(self, size: int, class_prior: dict,
                 aleatoric_sd: dict | None = None,
                 energy_multipliers: dict | None = None,
                 unknown_slip_prior: float = 0.25):
        self.size = size
        # per-cell geometric belief, stored as arrays for planner speed
        self.slope = np.zeros((size, size))
        self.roughness = np.full((size, size), 0.5)
        self.terrain_class = np.full((size, size), int(TerrainClass.SMOOTH_REGOLITH), dtype=np.int8)
        self.hazard_prob = np.full((size, size), 0.15)   # prior hazard rate
        self.illumination = np.full((size, size), 0.5)
        self.observed = np.zeros((size, size), dtype=bool)
        self.best_range = np.full((size, size), np.inf)

        # per-class mobility belief
        self.class_belief: dict[int, ClassBelief] = {}
        for k in range(N_TERRAIN_CLASSES):
            mean, variance = class_prior[k]
            self.class_belief[k] = ClassBelief(
                mean=mean, variance=variance,
                prior_mean=mean, prior_variance=variance,
            )
        # aleatoric (irreducible) spread per class, also a prior belief
        self.aleatoric_sd = aleatoric_sd or {k: 0.10 for k in range(N_TERRAIN_CLASSES)}
        self.unknown_slip_prior = unknown_slip_prior
        # Believed locomotion cost multiplier per class. Assuming 1.0 for
        # every class (the earlier behaviour) made the planner underestimate
        # every route through expensive ground by up to the true multiplier,
        # which is a systematic bias, not conservatism.
        self.energy_multiplier = dict(
            energy_multipliers or {k: 1.0 for k in range(N_TERRAIN_CLASSES)})
        self.energy_observations = {k: [] for k in range(N_TERRAIN_CLASSES)}

    # -- ingesting observations -------------------------------------------
    def ingest_observations(self, observations: dict) -> int:
        """Fold in remote sensing. Closer looks win over more distant ones."""
        updated = 0
        for (r, c), obs in observations.items():
            if obs["range"] > self.best_range[r, c]:
                continue
            self.best_range[r, c] = obs["range"]
            self.slope[r, c] = obs["slope"]
            self.roughness[r, c] = obs["roughness"]
            self.terrain_class[r, c] = obs["terrain_class"]
            self.illumination[r, c] = obs["illumination"]
            # confidence in a hazard call falls off with range
            confidence = float(np.clip(1.0 - obs["range"] / 12.0, 0.4, 0.97))
            self.hazard_prob[r, c] = confidence if obs["hazard"] else (1.0 - confidence)
            self.observed[r, c] = True
            updated += 1
        return updated

    def ingest_slip(self, record) -> None:
        """Fold in one proprioceptive mobility measurement.

        Base WorldModel stores the measurement but does NOT revise its class
        belief - that is what makes it the *fixed* model. AdaptiveWorldModel
        overrides this. Keeping the split here means the only difference
        between the fixed and adaptive conditions is this one method.
        """
        return None

    # -- queries used by planners -----------------------------------------
    def expected_slip(self, row: int, col: int) -> float:
        k = int(self.terrain_class[row, col])
        base = self.class_belief[k].mean if self.observed[row, col] else self.unknown_slip_prior
        return float(np.clip(base + 0.01 * self.slope[row, col], 0.0, 0.97))

    def slip_uncertainty(self, row: int, col: int) -> tuple[float, float]:
        """(epistemic_sd, aleatoric_sd) for the slip at a cell."""
        k = int(self.terrain_class[row, col])
        epistemic = self.class_belief[k].epistemic_sd
        aleatoric = self.aleatoric_sd[k]
        if not self.observed[row, col]:
            # never looked at this cell: inflate epistemic uncertainty rather
            # than pretending the class guess is trustworthy
            epistemic = float(np.hypot(epistemic, 0.12))
        return float(epistemic), float(aleatoric)

    def total_slip_sd(self, row: int, col: int) -> float:
        epistemic, aleatoric = self.slip_uncertainty(row, col)
        return float(np.hypot(epistemic, aleatoric))

    def believed_energy_multiplier(self, row: int, col: int) -> float:
        if not self.observed[row, col]:
            # unsurveyed ground: assume the average of what we believe about
            # the classes rather than the cheapest case
            return float(np.mean(list(self.energy_multiplier.values())))
        return float(self.energy_multiplier[int(self.terrain_class[row, col])])

    def expected_energy(self, row: int, col: int, distance: float,
                        gravity: float, energy_multiplier: float | None = None) -> float:
        from ..robot.power import locomotion_cost
        multiplier = (self.believed_energy_multiplier(row, col)
                      if energy_multiplier is None else energy_multiplier)
        return locomotion_cost(distance, float(self.slope[row, col]),
                               multiplier, self.expected_slip(row, col), gravity)

    def believed_traversable(self, row: int, col: int, max_slope_deg: float,
                             hazard_threshold: float = 0.5) -> bool:
        if not (0 <= row < self.size and 0 <= col < self.size):
            return False
        if self.hazard_prob[row, col] >= hazard_threshold:
            return False
        return bool(self.slope[row, col] <= max_slope_deg)

    def snapshot(self) -> dict:
        """Per-class belief summary, for logging and the dashboard."""
        return {
            int(k): {
                "mean": b.mean, "epistemic_sd": b.epistemic_sd,
                "n_observations": b.n_observations,
            }
            for k, b in self.class_belief.items()
        }


class AdaptiveWorldModel(WorldModel):
    """Identical to WorldModel except that it learns from what it drives on.

    This single override is the entire difference between the fixed and
    adaptive experimental conditions.
    """

    def ingest_slip(self, record) -> None:
        belief = self.class_belief[int(record.terrain_class)]
        # remove the slope contribution so the class belief is about the
        # terrain class itself, not about how steep this particular cell was
        slope_adjusted = float(np.clip(record.slip - 0.01 * record.slope, 0.0, 1.0))
        belief.update(slope_adjusted)

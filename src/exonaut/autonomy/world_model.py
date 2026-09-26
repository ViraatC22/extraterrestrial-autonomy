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

from dataclasses import dataclass

import numpy as np

from ..environments.base import N_TERRAIN_CLASSES, TerrainClass

# Assumed observation noise on a single slip measurement. Fixed and shared by
# every adaptive method so no method gains an advantage from a better-tuned
# noise model.
SLIP_OBS_VARIANCE = 0.02**2


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

    def __init__(
        self,
        size: int,
        class_prior: dict,
        aleatoric_sd: dict | None = None,
        energy_multipliers: dict | None = None,
        unknown_slip_prior: float = 0.25,
        epistemic_scale: float = 1.0,
    ):
        self.size = size
        #: Multiplies every reported epistemic (class-mean) standard deviation.
        #: 1.0 is the uncalibrated model (v1, and v2 as explored). A value fit
        #: on development data is the v2 calibration candidate; it applies to
        #: fixed and adaptive planners alike, so it gives neither an advantage.
        self.epistemic_scale = float(epistemic_scale)
        # per-cell geometric belief, stored as arrays for planner speed
        self.slope = np.zeros((size, size))
        self.roughness = np.full((size, size), 0.5)
        self.terrain_class = np.full((size, size), int(TerrainClass.SMOOTH_REGOLITH), dtype=np.int8)
        self.hazard_prob = np.full((size, size), 0.15)  # prior hazard rate
        self.illumination = np.full((size, size), 0.5)
        self.observed = np.zeros((size, size), dtype=bool)
        self.best_range = np.full((size, size), np.inf)

        # per-class mobility belief
        self.class_belief: dict[int, ClassBelief] = {}
        for k in range(N_TERRAIN_CLASSES):
            mean, variance = class_prior[k]
            self.class_belief[k] = ClassBelief(
                mean=mean,
                variance=variance,
                prior_mean=mean,
                prior_variance=variance,
            )
        # aleatoric (irreducible) spread per class, also a prior belief
        self.aleatoric_sd = aleatoric_sd or {k: 0.10 for k in range(N_TERRAIN_CLASSES)}
        self.unknown_slip_prior = unknown_slip_prior
        # Believed locomotion cost multiplier per class. Assuming 1.0 for
        # every class (the earlier behaviour) made the planner underestimate
        # every route through expensive ground by up to the true multiplier,
        # which is a systematic bias, not conservatism.
        # Note: only the slip belief is revised online. That is not a gap -
        # locomotion cost carries a 1/(1-slip) term, so a corrected slip
        # belief already corrects the energy estimate through the physics.
        # The per-class multiplier itself stays at its prior.
        self.energy_multiplier = dict(
            energy_multipliers or {k: 1.0 for k in range(N_TERRAIN_CLASSES)}
        )
        # class_mix and the derived unknown-terrain estimates are queried once
        # per A* node expansion, so they are cached and invalidated on write
        # rather than recomputed over the whole map each time.
        self._cache: dict = {}

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
        if updated:
            self._invalidate()
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
    def _invalidate(self) -> None:
        self._cache.clear()

    def class_mix(self) -> dict:
        """Empirical terrain-class frequencies among cells seen so far.

        Used to reason about ground that has not been looked at yet. Falls
        back to uniform before anything has been observed.
        """
        cached = self._cache.get("class_mix")
        if cached is not None:
            return cached
        if not self.observed.any():
            uniform = {k: 1.0 / N_TERRAIN_CLASSES for k in range(N_TERRAIN_CLASSES)}
            self._cache["class_mix"] = uniform
            return uniform
        seen = self.terrain_class[self.observed]
        counts = np.bincount(seen.astype(int), minlength=N_TERRAIN_CLASSES).astype(float)
        total = counts.sum()
        if total <= 0:
            mix = {k: 1.0 / N_TERRAIN_CLASSES for k in range(N_TERRAIN_CLASSES)}
        else:
            mix = {k: float(counts[k] / total) for k in range(N_TERRAIN_CLASSES)}
        self._cache["class_mix"] = mix
        return mix

    def unknown_slip_estimate(self) -> float:
        """Expected slip on terrain that has not been observed at all.

        This marginalizes the *current* class beliefs over the class mix
        actually encountered, so it moves as those beliefs move. A fixed
        constant here would discard the entire point of learning: a robot
        could measure that the local drift sand is treacherous and still plan
        its next route as though unseen ground were benign. Because routes
        are mostly made of not-yet-observed cells, that constant was what
        prevented adaptation from reaching any planning decision.
        """
        cached = self._cache.get("unknown_slip")
        if cached is not None:
            return cached
        mix = self.class_mix()
        value = float(sum(w * self.class_belief[k].mean for k, w in mix.items()))
        self._cache["unknown_slip"] = value
        return value

    def expected_slip(self, row: int, col: int) -> float:
        if self.observed[row, col]:
            base = self.class_belief[int(self.terrain_class[row, col])].mean
        else:
            base = self.unknown_slip_estimate()
        return float(np.clip(base + 0.01 * self.slope[row, col], 0.0, 0.97))

    def slip_uncertainty(self, row: int, col: int) -> tuple[float, float]:
        """(epistemic_sd, aleatoric_sd) for the slip at a cell."""
        if self.observed[row, col]:
            k = int(self.terrain_class[row, col])
            return (
                float(self.epistemic_scale * self.class_belief[k].epistemic_sd),
                float(self.aleatoric_sd[k]),
            )

        return self._unknown_uncertainty()

    def _unknown_uncertainty(self) -> tuple[float, float]:
        # Unobserved: the class itself is unknown, so epistemic uncertainty
        # must also cover the spread *between* class means, not just the
        # uncertainty within one class.
        cached = self._cache.get("unknown_uncertainty")
        if cached is not None:
            return cached
        mix = self.class_mix()
        mean = self.unknown_slip_estimate()
        between = float(
            np.sqrt(sum(w * (self.class_belief[k].mean - mean) ** 2 for k, w in mix.items()))
        )
        within = self.epistemic_scale * float(
            np.sqrt(sum(w * self.class_belief[k].variance for k, w in mix.items()))
        )
        aleatoric = float(sum(w * self.aleatoric_sd[k] for k, w in mix.items()))
        result = (float(np.hypot(between, within)), aleatoric)
        self._cache["unknown_uncertainty"] = result
        return result

    def total_slip_sd(self, row: int, col: int) -> float:
        epistemic, aleatoric = self.slip_uncertainty(row, col)
        return float(np.hypot(epistemic, aleatoric))

    # -- whole-map views, for visualisation ------------------------------
    # Vectorised equivalents of the per-cell queries above. They exist so the
    # interface can draw the robot's belief for every cell at once; tests
    # assert they agree with the per-cell functions, so a map drawn from them
    # shows exactly what the planner itself consults.
    def expected_slip_grid(self) -> np.ndarray:
        means = np.array([self.class_belief[k].mean for k in range(N_TERRAIN_CLASSES)])
        base = np.where(
            self.observed, means[self.terrain_class.astype(int)], self.unknown_slip_estimate()
        )
        return np.clip(base + 0.01 * self.slope, 0.0, 0.97)

    def total_slip_sd_grid(self) -> np.ndarray:
        epistemic = self.epistemic_scale * np.array(
            [self.class_belief[k].epistemic_sd for k in range(N_TERRAIN_CLASSES)]
        )
        aleatoric = np.array([self.aleatoric_sd[k] for k in range(N_TERRAIN_CLASSES)])
        classes = self.terrain_class.astype(int)
        observed_sd = np.hypot(epistemic[classes], aleatoric[classes])
        # every unobserved cell shares one estimate; row/col are ignored there
        unknown_epi, unknown_ale = self._unknown_uncertainty()
        return np.where(self.observed, observed_sd, float(np.hypot(unknown_epi, unknown_ale)))

    def believed_energy_multiplier(self, row: int, col: int) -> float:
        if not self.observed[row, col]:
            # unsurveyed ground: weight by the class mix actually encountered
            # rather than assuming the cheapest case
            cached = self._cache.get("unknown_energy_multiplier")
            if cached is not None:
                return cached
            mix = self.class_mix()
            value = float(sum(w * self.energy_multiplier[k] for k, w in mix.items()))
            self._cache["unknown_energy_multiplier"] = value
            return value
        return float(self.energy_multiplier[int(self.terrain_class[row, col])])

    def expected_energy(
        self,
        row: int,
        col: int,
        distance: float,
        gravity: float,
        energy_multiplier: float | None = None,
    ) -> float:
        from ..robot.power import locomotion_cost

        multiplier = (
            self.believed_energy_multiplier(row, col)
            if energy_multiplier is None
            else energy_multiplier
        )
        return locomotion_cost(
            distance, float(self.slope[row, col]), multiplier, self.expected_slip(row, col), gravity
        )

    def believed_traversable(
        self, row: int, col: int, max_slope_deg: float, hazard_threshold: float = 0.5
    ) -> bool:
        if not (0 <= row < self.size and 0 <= col < self.size):
            return False
        if self.hazard_prob[row, col] >= hazard_threshold:
            return False
        return bool(self.slope[row, col] <= max_slope_deg)

    def believed_traversable_grid(self, max_slope_deg: float, hazard_threshold: float = 0.5):
        """`believed_traversable` for every cell at once - for visualisation.

        Must agree with the per-cell method exactly; a test enforces it.
        """
        return (self.hazard_prob < hazard_threshold) & (self.slope <= max_slope_deg)

    def snapshot(self) -> dict:
        """Per-class belief summary, for logging and the dashboard."""
        return {
            int(k): {
                "mean": b.mean,
                "epistemic_sd": self.epistemic_scale * b.epistemic_sd,
                "n_observations": b.n_observations,
            }
            for k, b in self.class_belief.items()
        }


class AdaptiveWorldModel(WorldModel):
    """Identical to WorldModel except that it learns from what it drives on.

    This single override is the entire difference between the fixed and
    adaptive experimental conditions.
    """

    def __init__(self, *args, calibrated_update: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        #: v2 engine: per-reading variance includes the terrain's dispersion
        self.calibrated_update = calibrated_update

    def ingest_slip(self, record) -> None:
        # Update the class the robot currently believes occupies this cell.
        # ``record.terrain_class`` is simulator truth retained for evaluation;
        # consulting it here would let the autonomy stack see through sensor
        # misclassification and would be an information leak.
        believed_class = int(self.terrain_class[record.row, record.col])
        belief = self.class_belief[believed_class]
        # remove the slope contribution so the class belief is about the
        # terrain class itself, not about how steep this particular cell was
        slope_adjusted = float(np.clip(record.slip - 0.01 * record.slope, 0.0, 1.0))
        if self.calibrated_update:
            # v2: a reading scatters around the class mean by the terrain's own
            # dispersion, not just by sensor noise. Using only sensor noise
            # (v1) made one reading move the belief most of the way to itself.
            belief.update(
                slope_adjusted,
                obs_variance=self.aleatoric_sd[believed_class] ** 2 + SLIP_OBS_VARIANCE,
            )
        else:
            belief.update(slope_adjusted)
        self._invalidate()

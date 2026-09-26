"""Shared 2.5-D planetary terrain representation.

Scope statement (this is a scientific claim about what the model is, and it
belongs in the code as much as in the paper): this is **not** a high-fidelity
dynamics model of any specific flight rover or landing site. It is a
controlled 2.5-D autonomy testbed whose purpose is to expose different
decision-making algorithms to *identical* stochastic environments so their
decisions can be compared. Absolute numbers produced here are properties of
this model, not predictions of on-surface performance.

Every planetary body is expressed over the same terrain-class vocabulary
(`TerrainClass`) but with different class *parameters* and different class
*distributions*. That is deliberate and is the mechanism of the domain-shift
experiment: an autonomy stack calibrated on one body meets familiar feature
names whose underlying statistics have changed, which is precisely the
situation adaptive autonomy is supposed to handle.

Ground truth vs. belief: everything in `TerrainField` is ground truth held by
the simulator. The robot never reads it directly; it receives noisy, partial
observations through `robot/sensors.py` and maintains its own estimate in
`autonomy/world_model.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

import numpy as np


class TerrainClass(IntEnum):
    """Terrain vocabulary shared by every body.

    Shared names with body-specific statistics is what makes transfer
    meaningful: a world model can carry over its *structure* while its
    *parameters* must adapt.
    """

    SMOOTH_REGOLITH = 0
    ROCKY = 1
    LOOSE_FINES = 2  # deep dust / drift sand - the high-slip trap
    BEDROCK = 3  # exposed competent rock - best traction
    RIM_TALUS = 4  # crater rim debris - steep and rocky


N_TERRAIN_CLASSES = len(TerrainClass)


@dataclass(frozen=True)
class TerrainClassParams:
    """True physical parameters of one terrain class on one body.

    slip_mean / slip_dispersion parameterize the fraction of commanded motion
    lost to wheel slip. energy_multiplier scales locomotion cost. These are
    the quantities an adaptive world model must estimate online; a fixed
    planner is stuck with whatever prior it was given.
    """

    slip_mean: float
    slip_dispersion: float
    energy_multiplier: float
    label: str = ""

    def __post_init__(self):
        if not 0.0 <= self.slip_mean < 1.0:
            raise ValueError(f"slip_mean must be in [0,1), got {self.slip_mean}")
        if self.slip_dispersion < 0:
            raise ValueError("slip_dispersion must be non-negative")
        if self.energy_multiplier <= 0:
            raise ValueError("energy_multiplier must be positive")


@dataclass
class TerrainField:
    """Ground-truth terrain. Owned by the simulator, never read by a policy."""

    body: str
    size: int
    elevation: np.ndarray  # metres
    slope: np.ndarray  # degrees
    roughness: np.ndarray  # [0,1]
    terrain_class: np.ndarray  # int, values of TerrainClass
    illumination: np.ndarray  # [0,1] fraction of nominal solar flux
    hazard: np.ndarray  # bool, impassable
    class_params: dict  # TerrainClass -> TerrainClassParams
    gravity: float  # m/s^2, scales locomotion energy
    seed: int
    metadata: dict = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.size, self.size)

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.size and 0 <= col < self.size

    def is_traversable(self, row: int, col: int, max_slope_deg: float) -> bool:
        """Ground-truth traversability. The robot cannot call this for cells
        it has not observed; it works from its own belief instead."""
        if not self.in_bounds(row, col):
            return False
        if self.hazard[row, col]:
            return False
        return bool(self.slope[row, col] <= max_slope_deg)

    def params_at(self, row: int, col: int) -> TerrainClassParams:
        return self.class_params[TerrainClass(int(self.terrain_class[row, col]))]

    def true_slip_distribution(self, row: int, col: int, slope_penalty: float = 0.01):
        """Mean and dispersion of the slip fraction at a cell.

        Slope increases slip: climbing loses more traction than traversing
        flat ground. The linear-in-slope form is a deliberate simplification
        and is declared as such in the paper.
        """
        params = self.params_at(row, col)
        mean = params.slip_mean + slope_penalty * float(self.slope[row, col])
        return float(np.clip(mean, 0.0, 0.97)), params.slip_dispersion

    def true_slip_mean_grid(self, slope_penalty: float = 0.01) -> np.ndarray:
        """`true_slip_distribution`'s mean for every cell at once.

        For display and evaluation only (the rover never sees it). Must agree
        with the per-cell function exactly; a test enforces it, so the truth
        shown in the interface is the truth the simulator draws from.
        """
        class_means = np.array(
            [self.class_params[TerrainClass(k)].slip_mean for k in range(len(TerrainClass))]
        )
        mean = class_means[self.terrain_class.astype(int)] + slope_penalty * self.slope
        return np.clip(mean, 0.0, 0.97)


def derive_slope(elevation: np.ndarray, cell_size_m: float = 1.0) -> np.ndarray:
    """Slope in degrees from the elevation gradient."""
    dy, dx = np.gradient(elevation, cell_size_m)
    return np.degrees(np.arctan(np.sqrt(dy**2 + dx**2)))


def multi_octave_noise(
    size: int, rng: np.random.Generator, octaves: int = 4, persistence: float = 0.5
) -> np.ndarray:
    """Band-limited noise from a stack of randomly oriented sinusoids.

    Deliberately dependency-free and fully determined by `rng`, so a terrain
    is reproducible from its integer seed alone on any machine.
    """
    y, x = np.mgrid[0:size, 0:size].astype(np.float64)
    field_sum = np.zeros((size, size))
    amplitude = 1.0
    for octave in range(octaves):
        freq = (2**octave) / size
        angle = rng.uniform(0, 2 * np.pi)
        phase = rng.uniform(0, 2 * np.pi)
        u = x * np.cos(angle) + y * np.sin(angle)
        field_sum += amplitude * np.sin(2 * np.pi * freq * u + phase)
        amplitude *= persistence
    field_sum -= field_sum.min()
    denominator = field_sum.max()
    if denominator > 0:
        field_sum /= denominator
    return field_sum


def stamp_crater(elevation: np.ndarray, cy: float, cx: float, radius: float, depth: float) -> None:
    """Add a paraboloidal bowl with a raised rim, in place."""
    size = elevation.shape[0]
    y, x = np.mgrid[0:size, 0:size]
    dist = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
    inside = dist <= radius
    rim = (dist > radius) & (dist <= radius * 1.15)
    elevation[inside] += depth * ((dist[inside] / radius) ** 2 - 1.0)
    rim_height = depth * 0.15
    elevation[rim] += rim_height * (1.0 - (dist[rim] - radius) / (radius * 0.15))

"""Procedural lunar terrain generation.

Generates a square grid representing a patch of lunar surface with:
- an elevation heightmap (craters + rolling regolith noise)
- a slope map derived from elevation (rovers can't climb slopes past a limit)
- permanently shadowed regions (PSRs) near crater floors, where solar
  charging is unavailable, matching real lunar polar-crater geology
- a hazard mask combining slope and crater-rim rock density

No external noise library is used (keeps the dependency list short and the
generation fully reproducible from an integer seed) - elevation noise is
built from a small stack of random sine fields, which is enough texture for
the purposes of this simulation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Terrain:
    size: int
    elevation: np.ndarray
    slope: np.ndarray
    shadow_mask: np.ndarray
    hazard_mask: np.ndarray
    craters: list

    @property
    def shape(self) -> tuple[int, int]:
        return (self.size, self.size)

    def is_traversable(self, row: int, col: int, max_slope_deg: float) -> bool:
        if not (0 <= row < self.size and 0 <= col < self.size):
            return False
        if self.hazard_mask[row, col]:
            return False
        return self.slope[row, col] <= max_slope_deg


def _random_sine_field(size: int, rng: np.random.Generator, octaves: int = 4) -> np.ndarray:
    """Cheap multi-octave noise: sum of random-phase sine planes."""
    y, x = np.mgrid[0:size, 0:size].astype(np.float64)
    field = np.zeros((size, size))
    amplitude = 1.0
    for octave in range(octaves):
        freq = (2**octave) / size
        phase_x = rng.uniform(0, 2 * np.pi)
        phase_y = rng.uniform(0, 2 * np.pi)
        angle = rng.uniform(0, 2 * np.pi)
        u = x * np.cos(angle) + y * np.sin(angle)
        field += amplitude * np.sin(2 * np.pi * freq * u + phase_x + phase_y)
        amplitude *= 0.5
    field -= field.min()
    field /= max(field.max(), 1e-9)
    return field


def _stamp_crater(elevation: np.ndarray, cy: int, cx: int, radius: float, depth: float) -> None:
    size = elevation.shape[0]
    y, x = np.mgrid[0:size, 0:size]
    dist = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
    # Bowl-shaped depression with a slightly raised rim, matching simple
    # crater-morphology models used in lunar terrain teaching material.
    inside = dist <= radius
    rim = (dist > radius) & (dist <= radius * 1.15)
    bowl = depth * ((dist / radius) ** 2 - 1.0)
    elevation[inside] += bowl[inside]
    rim_height = depth * 0.15
    elevation[rim] += rim_height * (1.0 - (dist[rim] - radius) / (radius * 0.15))


def generate_terrain(
    size: int = 64,
    seed: int = 0,
    n_craters: int = 6,
    max_slope_deg: float = 25.0,
) -> Terrain:
    """Build a reproducible lunar terrain patch.

    Parameters
    ----------
    size: grid cells per side (square terrain).
    seed: RNG seed - identical seed always reproduces identical terrain,
        which matters for running the same terrain across algorithms in an
        experiment so the comparison is fair.
    n_craters: number of craters stamped onto the base regolith noise.
    max_slope_deg: slope (degrees) above which a cell counts as a hazard
        even if it isn't a rock/rim cell - used to seed the hazard mask;
        the actual per-rover traversability check is done again against
        the rover's own slope limit at query time.
    """
    rng = np.random.default_rng(seed)

    base_noise = _random_sine_field(size, rng, octaves=3)
    elevation = base_noise * 2.0  # meters of gentle regolith undulation

    craters = []
    for _ in range(n_craters):
        cy = rng.integers(int(size * 0.1), int(size * 0.9))
        cx = rng.integers(int(size * 0.1), int(size * 0.9))
        radius = rng.uniform(size * 0.04, size * 0.14)
        depth = rng.uniform(1.5, 6.0)
        _stamp_crater(elevation, cy, cx, radius, depth)
        craters.append(
            {"row": int(cy), "col": int(cx), "radius": float(radius), "depth": float(depth)}
        )

    # Slope: magnitude of the elevation gradient, converted to degrees.
    # Cell spacing is treated as 1 m, a reasonable scale for a rover-sized patch.
    dy, dx = np.gradient(elevation)
    slope = np.degrees(np.arctan(np.sqrt(dy**2 + dx**2)))

    # Permanently shadowed regions: crater floors below a depth threshold
    # and facing away from a fixed low sun-angle direction, approximating
    # PSRs found in real lunar polar craters (e.g. Shackleton).
    sun_dir = np.array([1.0, 0.3])
    sun_dir /= np.linalg.norm(sun_dir)
    shadow_mask = np.zeros((size, size), dtype=bool)
    for crater in craters:
        if crater["depth"] < 3.0:
            continue
        y, x = np.mgrid[0:size, 0:size]
        rel = np.stack([y - crater["row"], x - crater["col"]], axis=-1).astype(np.float64)
        dist = np.linalg.norm(rel, axis=-1)
        floor = dist <= crater["radius"] * 0.6
        # the half of the floor facing away from the sun stays shadowed
        with np.errstate(invalid="ignore"):
            facing = (rel[..., 0] * sun_dir[0] + rel[..., 1] * sun_dir[1]) / np.maximum(dist, 1e-6)
        away_from_sun = facing < -0.15
        shadow_mask |= floor & away_from_sun

    hazard_mask = slope > max_slope_deg
    for crater in craters:
        y, x = np.mgrid[0:size, 0:size]
        dist = np.sqrt((y - crater["row"]) ** 2 + (x - crater["col"]) ** 2)
        rim_rocks = (dist > crater["radius"]) & (dist <= crater["radius"] * 1.1)
        hazard_mask |= rim_rocks

    return Terrain(
        size=size,
        elevation=elevation,
        slope=slope,
        shadow_mask=shadow_mask,
        hazard_mask=hazard_mask,
        craters=craters,
    )

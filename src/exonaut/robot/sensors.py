"""Sensing model.

The robot never reads ground truth. It gets noisy observations of cells
within its sensing radius, and the noise grows with range - a stand-in for
the fact that terrain properties inferred from stereo imagery degrade with
distance from the camera. Two qualitatively different signals are provided,
and the distinction matters for the science:

  * **Remote observations** (this module) estimate *geometry* - slope,
    roughness, and a terrain-class guess. They are available at a distance
    but are only weak evidence about how the ground will actually behave.

  * **Proprioceptive slip measurements** (recorded when the robot drives, see
    vehicle.py) directly measure *mobility*. They are far more informative,
    but only for the single cell just driven.

That asymmetry is the entire reason online adaptation has something to do:
the only way to learn true terrain behaviour is to go and drive on it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..environments.base import N_TERRAIN_CLASSES, TerrainField


@dataclass
class SensorSuite:
    sensing_radius: int = 6
    slope_noise_deg: float = 1.2        # at zero range; grows with distance
    roughness_noise: float = 0.05
    class_confusion: float = 0.12       # P(misclassify) at zero range
    degradation: float = 0.0            # 0 = healthy, 1 = useless (fault state)

    def effective_radius(self) -> int:
        return max(1, int(round(self.sensing_radius * (1.0 - self.degradation))))

    def observe(self, terrain: TerrainField, row: int, col: int,
                rng: np.random.Generator) -> dict:
        """Return noisy observations of every cell within sensing range.

        Keys are (row, col); values are dicts of estimated properties plus
        the range at which they were taken, so the world model can weight
        near observations more heavily than far ones.
        """
        radius = self.effective_radius()
        noise_scale = 1.0 + 2.0 * self.degradation
        observations: dict[tuple[int, int], dict] = {}

        r0, r1 = max(0, row - radius), min(terrain.size, row + radius + 1)
        c0, c1 = max(0, col - radius), min(terrain.size, col + radius + 1)
        for r in range(r0, r1):
            for c in range(c0, c1):
                dist = float(np.hypot(r - row, c - col))
                if dist > radius:
                    continue
                # noise grows linearly with normalized range
                range_factor = 1.0 + dist / max(radius, 1)
                sigma_slope = self.slope_noise_deg * range_factor * noise_scale
                sigma_rough = self.roughness_noise * range_factor * noise_scale

                observed_class = int(terrain.terrain_class[r, c])
                confusion = min(0.95, self.class_confusion * range_factor * noise_scale)
                if rng.random() < confusion:
                    observed_class = int(rng.integers(0, N_TERRAIN_CLASSES))

                observations[(r, c)] = {
                    "slope": float(max(0.0, terrain.slope[r, c] + rng.normal(0, sigma_slope))),
                    "roughness": float(np.clip(
                        terrain.roughness[r, c] + rng.normal(0, sigma_rough), 0.0, 1.0)),
                    "terrain_class": observed_class,
                    "illumination": float(np.clip(
                        terrain.illumination[r, c] + rng.normal(0, 0.05 * range_factor),
                        0.0, 1.0)),
                    # Hazards are detected geometrically and are reliable close
                    # in, unreliable far out - a missed hazard at range is a
                    # real failure mode for this kind of robot.
                    "hazard": bool(terrain.hazard[r, c]) if rng.random() > 0.05 * range_factor
                              else bool(not terrain.hazard[r, c]),
                    "range": dist,
                }
        return observations

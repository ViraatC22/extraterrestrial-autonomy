"""Martian environment - the out-of-distribution body.

Qualitative differences from the lunar environment, and why each one is here:

  * **Aeolian bedforms.** Wind-blown drift sand forms extensive ripple fields
    rather than isolated pockets, so LOOSE_FINES is far more common and is
    organized into ridges that cut across a route instead of being avoidable
    puddles. Embedding in drift sand is the canonical way a real Mars rover
    loses mobility, which is why wheel slip is the standard traversability
    signal in Mars navigation work.
  * **Different slip statistics under the same class names.** Martian drift
    sand is substantially slippier than lunar fines in this model, and rock
    fields are less punishing. A world model calibrated on the Moon therefore
    carries the right *vocabulary* but the wrong *numbers* - exactly the
    failure mode adaptive autonomy is meant to survive.
  * **No permanent shadow, but a dimmer, variable sky.** Atmospheric opacity
    reduces and modulates insolation instead of eliminating it, so energy is
    tight everywhere rather than catastrophic in specific places.
  * **Higher gravity** raises locomotion energy for the same manoeuvre.

As with the lunar module, these values are chosen to create the qualitative
regimes the experiment needs and are not calibrated against measured Martian
geotechnical data.
"""

from __future__ import annotations

import numpy as np

from .base import (
    N_TERRAIN_CLASSES,
    TerrainClass,
    TerrainClassParams,
    TerrainField,
    derive_slope,
    multi_octave_noise,
    stamp_crater,
)

MARS_GRAVITY = 3.72  # m/s^2

# True per-class parameters for Mars. Note LOOSE_FINES is markedly worse than
# its lunar counterpart and BEDROCK slightly worse, while ROCKY is milder:
# the ordering of classes is not simply shifted, it is re-ranked.
MARS_CLASS_PARAMS = {
    TerrainClass.SMOOTH_REGOLITH: TerrainClassParams(0.12, 0.06, 1.10, "smooth drift"),
    TerrainClass.ROCKY: TerrainClassParams(0.14, 0.06, 1.30, "rock field"),
    TerrainClass.LOOSE_FINES: TerrainClassParams(0.62, 0.18, 2.40, "drift sand"),
    TerrainClass.BEDROCK: TerrainClassParams(0.06, 0.03, 1.00, "bedrock"),
    TerrainClass.RIM_TALUS: TerrainClassParams(0.26, 0.10, 1.60, "crater ejecta"),
}


def generate_mars_terrain(
    size: int = 64,
    seed: int = 0,
    n_craters: int = 4,
    max_slope_deg: float = 25.0,
    dune_fraction: float = 0.34,
    opacity: float = 0.35,
) -> TerrainField:
    rng = np.random.default_rng(seed)

    elevation = multi_octave_noise(size, rng, octaves=4) * 3.0

    # Aeolian ripple field: a directional, quasi-periodic bedform.
    y, x = np.mgrid[0:size, 0:size].astype(np.float64)
    wind_angle = rng.uniform(0, np.pi)
    ripple_axis = x * np.cos(wind_angle) + y * np.sin(wind_angle)
    ripple_wavelength = rng.uniform(5.0, 11.0)
    ripples = 0.5 * (1.0 + np.sin(2 * np.pi * ripple_axis / ripple_wavelength))
    elevation += 0.45 * ripples

    craters = []
    for _ in range(n_craters):
        cy = rng.integers(int(size * 0.1), int(size * 0.9))
        cx = rng.integers(int(size * 0.1), int(size * 0.9))
        radius = rng.uniform(size * 0.05, size * 0.13)
        depth = rng.uniform(1.0, 4.5)
        stamp_crater(elevation, cy, cx, radius, depth)
        craters.append(
            {"row": int(cy), "col": int(cx), "radius": float(radius), "depth": float(depth)}
        )

    slope = derive_slope(elevation)
    roughness = multi_octave_noise(size, rng, octaves=5)

    terrain_class = np.full((size, size), int(TerrainClass.SMOOTH_REGOLITH), dtype=np.int8)
    terrain_class[roughness > 0.66] = int(TerrainClass.ROCKY)
    terrain_class[(slope < 2.5) & (roughness < 0.22)] = int(TerrainClass.BEDROCK)

    # Drift sand accumulates in ripple troughs - spatially extensive, and
    # arranged in bands that a route has to either cross or go around.
    dune_cut = np.quantile(ripples, 1.0 - dune_fraction)
    terrain_class[ripples >= dune_cut] = int(TerrainClass.LOOSE_FINES)

    hazard = slope > max_slope_deg
    for crater in craters:
        yy, xx = np.mgrid[0:size, 0:size]
        dist = np.sqrt((yy - crater["row"]) ** 2 + (xx - crater["col"]) ** 2)
        ejecta = (dist > crater["radius"]) & (dist <= crater["radius"] * 1.15)
        terrain_class[ejecta] = int(TerrainClass.RIM_TALUS)
        hazard |= (dist > crater["radius"]) & (dist <= crater["radius"] * 1.03)

    # Dusty sky: dimmer everywhere, spatially modulated, never fully dark.
    haze = multi_octave_noise(size, rng, octaves=2)
    illumination = (1.0 - opacity) * (0.75 + 0.25 * haze)
    illumination *= np.clip(1.0 - slope / 90.0, 0.25, 1.0)
    illumination = np.clip(illumination, 0.05, 1.0)

    return TerrainField(
        body="mars",
        size=size,
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        terrain_class=terrain_class,
        illumination=illumination,
        hazard=hazard,
        class_params=dict(MARS_CLASS_PARAMS),
        gravity=MARS_GRAVITY,
        seed=seed,
        metadata={
            "craters": craters,
            "max_slope_deg": max_slope_deg,
            "wind_angle": float(wind_angle),
            "opacity": opacity,
            "n_classes": N_TERRAIN_CLASSES,
        },
    )

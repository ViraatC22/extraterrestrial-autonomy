"""Lunar polar environment.

Qualitative features modeled: heavily cratered relief, rocky rim talus,
pockets of deep fine regolith, and permanently shadowed regions (PSRs) on
crater floors where a solar-powered robot gets no recharge at all. Risk-aware
exploration of shadowed lunar regions under an energy budget is an active
planetary-autonomy research problem, and the PSR is what makes energy a
genuinely binding constraint here rather than a bookkeeping detail.

Parameter values below are chosen to produce the qualitative regimes the
experiment needs (a low-traction trap, a high-traction refuge, steep
impassable rims, and true darkness). They are NOT calibrated against measured
lunar geotechnical data, and the paper says so explicitly.
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

LUNAR_GRAVITY = 1.62  # m/s^2

# True per-class parameters for the Moon.
LUNAR_CLASS_PARAMS = {
    TerrainClass.SMOOTH_REGOLITH: TerrainClassParams(0.08, 0.04, 1.00, "smooth regolith"),
    TerrainClass.ROCKY: TerrainClassParams(0.18, 0.07, 1.45, "rocky"),
    TerrainClass.LOOSE_FINES: TerrainClassParams(0.42, 0.14, 1.90, "deep fines"),
    TerrainClass.BEDROCK: TerrainClassParams(0.04, 0.02, 0.95, "bedrock"),
    TerrainClass.RIM_TALUS: TerrainClassParams(0.30, 0.12, 1.75, "rim talus"),
}


def generate_lunar_terrain(
    size: int = 64,
    seed: int = 0,
    n_craters: int = 7,
    max_slope_deg: float = 25.0,
    fines_fraction: float = 0.18,
) -> TerrainField:
    rng = np.random.default_rng(seed)

    elevation = multi_octave_noise(size, rng, octaves=3) * 2.0
    craters = []
    for _ in range(n_craters):
        cy = rng.integers(int(size * 0.1), int(size * 0.9))
        cx = rng.integers(int(size * 0.1), int(size * 0.9))
        radius = rng.uniform(size * 0.05, size * 0.15)
        depth = rng.uniform(1.5, 6.5)
        stamp_crater(elevation, cy, cx, radius, depth)
        craters.append(
            {"row": int(cy), "col": int(cx), "radius": float(radius), "depth": float(depth)}
        )

    slope = derive_slope(elevation)
    roughness = multi_octave_noise(size, rng, octaves=5)

    # --- terrain classes -------------------------------------------------
    terrain_class = np.full((size, size), int(TerrainClass.SMOOTH_REGOLITH), dtype=np.int8)
    terrain_class[roughness > 0.62] = int(TerrainClass.ROCKY)
    terrain_class[slope < 3.0] = np.where(
        roughness[slope < 3.0] < 0.25,
        int(TerrainClass.BEDROCK),
        terrain_class[slope < 3.0],
    )

    # Deep fines collect in low-lying, low-roughness pockets: the slip trap.
    fines_field = multi_octave_noise(size, rng, octaves=2)
    low_ground = elevation < np.quantile(elevation, 0.45)
    fines_cut = np.quantile(fines_field, 1.0 - fines_fraction)
    terrain_class[(fines_field >= fines_cut) & low_ground] = int(TerrainClass.LOOSE_FINES)

    hazard = slope > max_slope_deg
    for crater in craters:
        y, x = np.mgrid[0:size, 0:size]
        dist = np.sqrt((y - crater["row"]) ** 2 + (x - crater["col"]) ** 2)
        rim_band = (dist > crater["radius"]) & (dist <= crater["radius"] * 1.12)
        terrain_class[rim_band] = int(TerrainClass.RIM_TALUS)
        hazard |= (dist > crater["radius"]) & (dist <= crater["radius"] * 1.04)

    # --- illumination ----------------------------------------------------
    # Low sun angle typical of polar terrain: crater floors facing away from
    # the sun receive nothing, which is the PSR.
    sun = np.array([1.0, 0.3])
    sun /= np.linalg.norm(sun)
    illumination = np.full((size, size), 0.85)
    for crater in craters:
        if crater["depth"] < 3.0:
            continue
        y, x = np.mgrid[0:size, 0:size]
        rel_y = y - crater["row"]
        rel_x = x - crater["col"]
        dist = np.sqrt(rel_y**2 + rel_x**2)
        with np.errstate(invalid="ignore", divide="ignore"):
            facing = (rel_y * sun[0] + rel_x * sun[1]) / np.maximum(dist, 1e-6)
        shadowed = (dist <= crater["radius"] * 0.65) & (facing < -0.15)
        illumination[shadowed] = 0.0
    # gentle large-scale variation from local slope aspect
    illumination *= np.clip(1.0 - slope / 90.0, 0.25, 1.0)
    illumination = np.clip(illumination, 0.0, 1.0)

    return TerrainField(
        body="moon",
        size=size,
        elevation=elevation,
        slope=slope,
        roughness=roughness,
        terrain_class=terrain_class,
        illumination=illumination,
        hazard=hazard,
        class_params=dict(LUNAR_CLASS_PARAMS),
        gravity=LUNAR_GRAVITY,
        seed=seed,
        metadata={
            "craters": craters,
            "max_slope_deg": max_slope_deg,
            "n_classes": N_TERRAIN_CLASSES,
        },
    )

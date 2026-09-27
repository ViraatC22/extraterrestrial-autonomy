"""Planetary environments.

`make_environment(body, seed, ...)` is the single entry point used by the
experiment runner, so a trial is fully specified by (body, seed, config).
"""

from __future__ import annotations

import numpy as np

from .base import (
    N_TERRAIN_CLASSES,
    TerrainClass,
    TerrainClassParams,
    TerrainField,
)
from .lunar import LUNAR_CLASS_PARAMS, generate_lunar_terrain
from .mars import MARS_CLASS_PARAMS, generate_mars_terrain

BODIES = ("moon", "mars")

_GENERATORS = {
    "moon": generate_lunar_terrain,
    "mars": generate_mars_terrain,
}

TRUE_CLASS_PARAMS = {
    "moon": LUNAR_CLASS_PARAMS,
    "mars": MARS_CLASS_PARAMS,
}


#: Decimal places kept by `canonicalize`. Platform floating-point noise in the
#: generators (sin, cos, arctan from different maths libraries) is ~1e-15
#: relative. Rounding makes both platforms agree unless a value lies within
#: that noise of a rounding boundary: probability ~ 2e-15 / 10^-d per value,
#: times ~16,000 values per map. At d = 9 that is ~3% of maps (measured on
#: validation: 4 of 800 maps); at d = 6, ~3e-5. Six decimals is still six
#: orders of magnitude below the smallest physically meaningful difference
#: (slope-sensor noise 1.2 degrees; roughness noise 0.05). Chosen from this
#: calculation, not from mission outcomes.
CANONICAL_DECIMALS = 6


def canonicalize(terrain: TerrainField) -> TerrainField:
    """Round the continuous terrain fields so every platform gets the same bits.

    Used by engine v2 only (v1 keeps its terrain exactly as generated, so the
    Study 1 missions reproduce). Discrete fields (class, hazard) are untouched;
    they are already identical across platforms. See NUMERICAL_REPRODUCIBILITY.md.
    """
    for name in ("elevation", "slope", "roughness", "illumination"):
        setattr(terrain, name, np.round(getattr(terrain, name), CANONICAL_DECIMALS))
    return terrain


def make_environment(body: str, seed: int, size: int = 64, **kwargs) -> TerrainField:
    if body not in _GENERATORS:
        raise ValueError(f"unknown body {body!r}; expected one of {BODIES}")
    # Every terrain in the project is built here, so this is where the v2
    # confirmatory seeds are protected: unauthorized use raises and is logged.
    from ..experiments.v2_protocol import guard_seed

    guard_seed(seed)
    return _GENERATORS[body](size=size, seed=seed, **kwargs)


__all__ = [
    "BODIES",
    "N_TERRAIN_CLASSES",
    "TRUE_CLASS_PARAMS",
    "TerrainClass",
    "TerrainClassParams",
    "TerrainField",
    "make_environment",
    "generate_lunar_terrain",
    "generate_mars_terrain",
]

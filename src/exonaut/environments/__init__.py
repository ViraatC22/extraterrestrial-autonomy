"""Planetary environments.

`make_environment(body, seed, ...)` is the single entry point used by the
experiment runner, so a trial is fully specified by (body, seed, config).
"""

from __future__ import annotations

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

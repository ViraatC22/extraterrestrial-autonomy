"""Artificial potential field exploration.

Each rover sums three forces computed from its own known-map:
  - attraction toward nearby frontier cells (pulls it toward unexplored area)
  - repulsion from other rovers it currently knows the position of (spreads
    the swarm out instead of clumping, the classic APF coordination trick)
  - repulsion from known nearby hazard cells (steers around craters/slopes)

The resulting vector is converted to the nearest discrete action.
"""

from __future__ import annotations

import numpy as np

from ..comms import observable_teammates
from ..rover import STAY_ACTION, best_traversable_action

ATTRACT_GAIN = 1.0
ROVER_REPEL_GAIN = 3.0
ROVER_REPEL_RADIUS = 6.0
HAZARD_REPEL_GAIN = 2.0
HAZARD_REPEL_RADIUS = 3.0
FRONTIER_SAMPLE = 25  # nearest-N frontiers considered, for speed on large maps


def potential_field_policy(env, rover_id: int) -> int:
    rover = next(r for r in env.rovers if r.rover_id == rover_id)
    rr, rc = float(rover.row), float(rover.col)
    fx, fy = 0.0, 0.0

    frontiers = rover.frontier_cells(env.terrain)
    if frontiers:
        frontiers.sort(key=lambda cell: (cell[0] - rr) ** 2 + (cell[1] - rc) ** 2)
        for r, c in frontiers[:FRONTIER_SAMPLE]:
            dr, dc = r - rr, c - rc
            dist = max((dr**2 + dc**2) ** 0.5, 1e-6)
            fx += ATTRACT_GAIN * dr / dist**1.5
            fy += ATTRACT_GAIN * dc / dist**1.5

    # Only repel from teammates this rover could actually locate - ones it can
    # see, or ones reachable over the mesh. Using every rover's true position
    # would make dispersion immune to the communication radius under study.
    for other in observable_teammates(env, rover):
        dr, dc = other.row - rr, other.col - rc
        dist = (dr**2 + dc**2) ** 0.5
        if 0 < dist <= ROVER_REPEL_RADIUS:
            fx -= ROVER_REPEL_GAIN * dr / dist**3
            fy -= ROVER_REPEL_GAIN * dc / dist**3

    terrain = env.terrain
    r0, r1 = (
        max(0, rover.row - int(HAZARD_REPEL_RADIUS)),
        min(terrain.size, rover.row + int(HAZARD_REPEL_RADIUS) + 1),
    )
    c0, c1 = (
        max(0, rover.col - int(HAZARD_REPEL_RADIUS)),
        min(terrain.size, rover.col + int(HAZARD_REPEL_RADIUS) + 1),
    )
    hazard_local = terrain.hazard_mask[r0:r1, c0:c1]
    if hazard_local.any():
        hr, hc = np.nonzero(hazard_local)
        for hry, hcx in zip(hr + r0, hc + c0, strict=False):
            dr, dc = float(hry) - rr, float(hcx) - rc
            dist = (dr**2 + dc**2) ** 0.5
            if 0 < dist <= HAZARD_REPEL_RADIUS:
                fx -= HAZARD_REPEL_GAIN * dr / dist**3
                fy -= HAZARD_REPEL_GAIN * dc / dist**3

    if fx == 0.0 and fy == 0.0:
        return STAY_ACTION
    return best_traversable_action(env.terrain, rover.row, rover.col, fx, fy, rover.max_slope_deg)

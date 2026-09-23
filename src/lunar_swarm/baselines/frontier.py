"""Greedy nearest-frontier exploration.

Classic single-robot exploration heuristic, applied independently by every
rover with no explicit coordination beyond whatever map knowledge it has
received over the mesh (see comms.py). Rovers frequently converge on the
same frontier when they can't see each other's intentions - that
uncoordinated behavior is itself part of the comparison against the RL
policy, not a bug to be fixed here.
"""
from __future__ import annotations

from ..rover import STAY_ACTION, best_traversable_action


def frontier_policy(env, rover_id: int) -> int:
    rover = next(r for r in env.rovers if r.rover_id == rover_id)
    frontiers = rover.frontier_cells(env.terrain)
    if not frontiers:
        return STAY_ACTION
    rr, rc = rover.row, rover.col
    target = min(frontiers, key=lambda cell: (cell[0] - rr) ** 2 + (cell[1] - rc) ** 2)
    return best_traversable_action(env.terrain, rr, rc, target[0] - rr, target[1] - rc, rover.max_slope_deg)

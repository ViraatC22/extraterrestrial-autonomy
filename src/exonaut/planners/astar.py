"""Shortest-path A* - the deterministic control condition.

Minimizes geometric distance and nothing else. It will happily route straight
through believed-benign drift sand because distance is all it scores. This is
not a strawman: it is what a planner does when it has no model of terrain
risk at all, and it establishes the floor the other methods must beat.
"""

from __future__ import annotations

from .base import Planner


class ShortestPathPlanner(Planner):
    name = "astar"
    adaptive = False

    def step_cost(self, world_model, from_cell, to_cell, distance: float) -> float:
        return distance

    def min_step_cost(self) -> float:
        return 1.0

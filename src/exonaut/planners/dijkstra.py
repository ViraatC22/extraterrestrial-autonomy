"""Dijkstra - uniform-cost search.

Included as an explicit control for the *heuristic*, not for the cost
function. It expands the same cost surface as `ShortestPathPlanner` but with
no heuristic guidance, so comparing the two isolates what A*'s heuristic buys
in search effort while leaving the returned path unchanged. Any difference in
mission outcome between them would indicate a bug in the heuristic's
admissibility, which makes this a useful diagnostic as well as a baseline.
"""

from __future__ import annotations

from .base import Planner


class DijkstraPlanner(Planner):
    name = "dijkstra"
    adaptive = False

    def step_cost(self, world_model, from_cell, to_cell, distance: float) -> float:
        return distance

    def heuristic(self, cell, goal) -> float:
        # Zero heuristic reduces A* to uniform-cost search.
        return 0.0

    def min_step_cost(self) -> float:
        return 1.0

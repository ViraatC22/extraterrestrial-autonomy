"""Common planner interface and the shared A* search core.

Every planner in this project answers the same question - "give me a route
from A to B" - and differs only in the *cost* it assigns to entering a cell
and whether it revises that cost as evidence arrives. Sharing one search
implementation is deliberate: it means a measured difference between planners
is a difference in their objective, not in the quality of someone's A*.
"""

from __future__ import annotations

import heapq
from abc import ABC, abstractmethod

import numpy as np

NEIGHBOURS = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]


class Planner(ABC):
    """A* over a planner-specific cost function."""

    name = "base"
    #: Whether this planner revises its world model from driving experience.
    adaptive = False

    def __init__(
        self, max_slope_deg: float = 25.0, hazard_threshold: float = 0.5, gravity: float = 1.62
    ):
        self.max_slope_deg = max_slope_deg
        self.hazard_threshold = hazard_threshold
        self.gravity = gravity
        self.nodes_expanded = 0
        self.plan_calls = 0

    @abstractmethod
    def step_cost(self, world_model, from_cell, to_cell, distance: float) -> float:
        """Cost of moving between adjacent cells, under this planner's
        objective. Must be non-negative for A* to be correct."""

    def heuristic(self, cell, goal) -> float:
        """Octile distance scaled by the cheapest possible per-cell cost.

        Kept admissible (never over-estimating) so A* returns an optimal path
        under the planner's own cost function.
        """
        dr = abs(cell[0] - goal[0])
        dc = abs(cell[1] - goal[1])
        octile = (dr + dc) + (np.sqrt(2.0) - 2.0) * min(dr, dc)
        return float(octile * self.min_step_cost())

    def min_step_cost(self) -> float:
        """Lower bound on any single step's cost, for heuristic scaling."""
        return 1.0

    def passable(self, world_model, row, col) -> bool:
        return world_model.believed_traversable(row, col, self.max_slope_deg, self.hazard_threshold)

    def plan(self, world_model, start, goal) -> list:
        """A* from start to goal over the believed world. Returns a list of
        cells including both endpoints, or [] if no route is believed to
        exist."""
        self.plan_calls += 1
        if start == goal:
            return [start]
        size = world_model.size
        if not (0 <= goal[0] < size and 0 <= goal[1] < size):
            return []

        open_heap = [(self.heuristic(start, goal), 0.0, start)]
        came_from: dict = {}
        best_cost = {start: 0.0}
        closed = set()

        while open_heap:
            _, cost, current = heapq.heappop(open_heap)
            if current in closed:
                continue
            closed.add(current)
            self.nodes_expanded += 1

            if current == goal:
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                return path[::-1]

            for dr, dc in NEIGHBOURS:
                neighbour = (current[0] + dr, current[1] + dc)
                if neighbour in closed:
                    continue
                if not (0 <= neighbour[0] < size and 0 <= neighbour[1] < size):
                    continue
                # The goal itself is always enterable: a science target may sit
                # on ground the robot is unsure about, and refusing to plan to
                # it at all would silently drop targets.
                if neighbour != goal and not self.passable(world_model, *neighbour):
                    continue
                distance = float(np.hypot(dr, dc))
                step = self.step_cost(world_model, current, neighbour, distance)
                if step < 0:
                    raise ValueError(f"{self.name}: negative step cost {step}")
                new_cost = cost + step
                if new_cost < best_cost.get(neighbour, np.inf):
                    best_cost[neighbour] = new_cost
                    came_from[neighbour] = current
                    heapq.heappush(
                        open_heap,
                        (new_cost + self.heuristic(neighbour, goal), new_cost, neighbour),
                    )
        return []

    def observe_slip(self, world_model, record) -> None:
        """Hook called after every drive attempt. Non-adaptive planners
        ignore it; adaptive ones use it to revise their world model."""
        return None

    def reset_stats(self) -> None:
        self.nodes_expanded = 0
        self.plan_calls = 0

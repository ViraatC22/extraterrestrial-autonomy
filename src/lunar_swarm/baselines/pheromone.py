"""Stigmergic (ant-colony-inspired) exploration.

Rovers deposit 'visited' pheromone on the terrain itself as they pass; it
decays each step. Each rover steers toward the lowest-pheromone,
least-known cell in its local sensing neighborhood - an avoid-what's-
already-covered heuristic. Unlike the other two baselines, coordination
here needs no radio communication at all: the shared physical terrain is
the coordination channel, exactly as in real ant colonies. One
PheromonePolicy instance is shared by every rover in a trial (there's one
pheromone field on the ground, not one per rover) - construct a fresh
instance per trial so pheromone doesn't leak between runs.
"""
from __future__ import annotations

import numpy as np

from ..rover import STAY_ACTION, best_traversable_action


class PheromonePolicy:
    def __init__(self, decay: float = 0.98, deposit: float = 5.0, explore_radius: int | None = None):
        self.decay = decay
        self.deposit = deposit
        # None means "bounded by the rover's own sensing radius". A rover
        # cannot perceive pheromone or terrain it cannot sense, so candidate
        # cells must not extend past R_s - otherwise this policy would be
        # reading terrain the other policies are not allowed to see.
        self.explore_radius = explore_radius
        self._pheromone: np.ndarray | None = None
        self._last_step = -1

    def _ensure_grid(self, env) -> None:
        if self._pheromone is None:
            self._pheromone = np.zeros(env.terrain.shape)
        if env.step_count != self._last_step:
            self._pheromone *= self.decay
            self._last_step = env.step_count

    def __call__(self, env, rover_id: int) -> int:
        self._ensure_grid(env)
        rover = next(r for r in env.rovers if r.rover_id == rover_id)
        self._pheromone[rover.row, rover.col] += self.deposit

        terrain = env.terrain
        radius = self.explore_radius if self.explore_radius is not None else rover.sensor_radius
        r0 = max(0, rover.row - radius)
        r1 = min(terrain.size, rover.row + radius + 1)
        c0 = max(0, rover.col - radius)
        c1 = min(terrain.size, rover.col + radius + 1)

        best_score, target = np.inf, None
        for r in range(r0, r1):
            for c in range(c0, c1):
                if terrain.hazard_mask[r, c]:
                    continue
                dist = ((r - rover.row) ** 2 + (c - rover.col) ** 2) ** 0.5
                if dist == 0 or dist > radius:
                    continue
                known_penalty = 4.0 if (r, c) in rover.known else 0.0
                score = self._pheromone[r, c] + known_penalty * 5.0 + dist * 0.1
                if score < best_score:
                    best_score = score
                    target = (r, c)

        if target is None:
            return STAY_ACTION
        return best_traversable_action(
            terrain, rover.row, rover.col, target[0] - rover.row, target[1] - rover.col, rover.max_slope_deg,
        )

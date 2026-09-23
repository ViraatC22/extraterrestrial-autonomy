"""Multi-rover lunar exploration environment.

This is the core simulation loop shared by every algorithm tested in the
project (classical baselines and the RL policy alike), so that comparisons
between algorithms are only measuring the algorithm's decisions, not
differences in the world they're run against.

Usage pattern:
    env = SwarmEnv(config)
    obs = env.reset()
    while not env.done:
        actions = {rid: policy(env, rid) for rid in env.rover_ids}
        obs = env.step(actions)
    metrics = env.metrics()
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .rover import Rover, N_ACTIONS, STAY_ACTION
from .terrain import Terrain, generate_terrain
from . import comms


@dataclass
class EnvConfig:
    terrain_size: int = 64
    n_craters: int = 6
    n_rovers: int = 4
    sensor_radius: int = 4
    comm_radius: int = 12
    max_slope_deg: float = 25.0
    max_steps: int = 400
    seed: int = 0
    # fraction of rovers randomly disabled partway through the run, to test
    # resilience of the swarm - the "attrition" independent variable.
    failure_rate: float = 0.0
    failure_step_frac: float = 0.5


class SwarmEnv:
    def __init__(self, config: EnvConfig):
        self.config = config
        self.terrain: Terrain | None = None
        self.rovers: list[Rover] = []
        self.coverage: np.ndarray | None = None
        self.step_count = 0
        self.done = False
        self._history: list[dict] = []
        self.reset()

    # -- setup -----------------------------------------------------------
    def _find_spawn_cluster(self, cfg: EnvConfig) -> tuple[int, int]:
        """Locate a base-station cell near the map center whose local
        neighborhood is mostly hazard-free. Placing the whole swarm at the
        literal center regardless of terrain (the old behavior) could drop
        rovers right at a crater rim, boxing them in on step 0 no matter
        which algorithm is driving them."""
        size = cfg.terrain_size
        center = size // 2
        search = max(4, size // 6)
        best, best_score = (center, center), -1.0
        for r in range(max(0, center - search), min(size, center + search)):
            for c in range(max(0, center - search), min(size, center + search)):
                if not self.terrain.is_traversable(r, c, cfg.max_slope_deg):
                    continue
                r0, r1 = max(0, r - 3), min(size, r + 4)
                c0, c1 = max(0, c - 3), min(size, c + 4)
                local_hazard = self.terrain.hazard_mask[r0:r1, c0:c1].mean()
                score = 1.0 - local_hazard
                if score > best_score:
                    best_score = score
                    best = (r, c)
        return best

    def reset(self) -> dict:
        cfg = self.config
        self.terrain = generate_terrain(
            size=cfg.terrain_size, seed=cfg.seed, n_craters=cfg.n_craters,
            max_slope_deg=cfg.max_slope_deg,
        )
        rng = np.random.default_rng(cfg.seed + 1000)
        self.rovers = []
        base_row, base_col = self._find_spawn_cluster(cfg)
        # spawn cluster near the lander/base station, like a real mission
        occupied: set[tuple[int, int]] = set()
        placed = 0
        attempts = 0
        radius = 1
        while placed < cfg.n_rovers and attempts < 3000:
            attempts += 1
            r = base_row + rng.integers(-radius, radius + 1)
            c = base_col + rng.integers(-radius, radius + 1)
            if (r, c) not in occupied and self.terrain.is_traversable(r, c, cfg.max_slope_deg):
                occupied.add((r, c))
                self.rovers.append(Rover(
                    rover_id=placed, row=int(r), col=int(c),
                    sensor_radius=cfg.sensor_radius, comm_radius=cfg.comm_radius,
                    max_slope_deg=cfg.max_slope_deg,
                ))
                placed += 1
            if attempts % 100 == 0:
                radius = min(radius + 1, cfg.terrain_size // 3)
        self.coverage = np.zeros((cfg.terrain_size, cfg.terrain_size), dtype=bool)
        self.step_count = 0
        self.done = False
        self._history = []
        self._failed_this_run = False
        for rover in self.rovers:
            self._apply_sense(rover)
        comms.sync_mesh(self.rovers, cfg.comm_radius)
        return self.observations()

    @property
    def rover_ids(self) -> list[int]:
        return [r.rover_id for r in self.rovers if r.alive]

    @property
    def history(self) -> list[dict]:
        return self._history

    # -- stepping ----------------------------------------------------------
    def _apply_sense(self, rover: Rover) -> None:
        rover.sense(self.terrain)
        for (r, c) in rover.known:
            self.coverage[r, c] = True

    def _maybe_inject_failures(self) -> None:
        cfg = self.config
        if cfg.failure_rate <= 0 or self._failed_this_run:
            return
        if self.step_count < int(cfg.max_steps * cfg.failure_step_frac):
            return
        rng = np.random.default_rng(cfg.seed + 5000 + self.step_count)
        n_to_fail = int(round(cfg.failure_rate * len(self.rovers)))
        alive = [r for r in self.rovers if r.alive]
        if n_to_fail > 0 and alive:
            victims = rng.choice(alive, size=min(n_to_fail, len(alive)), replace=False)
            for v in victims:
                v.alive = False
        self._failed_this_run = True

    def step(self, actions: dict[int, int]) -> dict:
        cfg = self.config
        by_id = {r.rover_id: r for r in self.rovers}
        for rid, action in actions.items():
            rover = by_id.get(rid)
            if rover is None or not rover.alive:
                continue
            rover.try_move(int(action), self.terrain)
            in_shadow = bool(self.terrain.shadow_mask[rover.row, rover.col])
            rover.apply_solar(in_shadow)
            self._apply_sense(rover)

        comms.sync_mesh(self.rovers, cfg.comm_radius)
        self._maybe_inject_failures()

        self.step_count += 1
        coverage_frac = float(self.coverage[~self.terrain.hazard_mask].mean())
        self._history.append({
            "step": self.step_count,
            "coverage": coverage_frac,
            "alive": sum(1 for r in self.rovers if r.alive),
            "mean_battery": float(np.mean([r.battery for r in self.rovers if r.alive])) if any(r.alive for r in self.rovers) else 0.0,
        })

        all_dead = not any(r.alive for r in self.rovers)
        full_coverage = coverage_frac >= 0.995
        self.done = all_dead or full_coverage or self.step_count >= cfg.max_steps
        return self.observations()

    # -- observation / metrics ---------------------------------------------
    def observations(self) -> dict:
        return {rid: self.observe(rid) for rid in self.rover_ids}

    def observe(self, rover_id: int) -> dict:
        rover = next(r for r in self.rovers if r.rover_id == rover_id)
        return {
            "pos": rover.pos,
            "battery": rover.battery,
            "known": rover.known,
            "frontiers": rover.frontier_cells(self.terrain),
        }

    def metrics(self) -> dict:
        hist = self._history
        final_coverage = hist[-1]["coverage"] if hist else 0.0
        energy_used = sum(
            max(0.0, 100.0 - r.battery) + (100.0 if not r.alive else 0.0)
            for r in self.rovers
        )
        return {
            "final_coverage": final_coverage,
            "steps_taken": self.step_count,
            "rovers_alive": sum(1 for r in self.rovers if r.alive),
            "n_rovers": len(self.rovers),
            "energy_used": energy_used,
            "coverage_per_energy": final_coverage / max(energy_used, 1e-6),
            "history": hist,
        }

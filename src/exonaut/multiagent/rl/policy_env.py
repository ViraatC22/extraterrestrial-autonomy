"""Gymnasium adapter that turns the multi-rover SwarmEnv into a trainable
single-agent problem via parameter sharing.

Why this design: SwarmEnv is inherently multi-agent, but training a true
self-play multi-agent policy from scratch is a research-level undertaking
on its own. The standard simplification used here - and disclosed as such
in docs/METHODOLOGY.md - is:

  - one rover (the "learner") is controlled by the policy being trained
  - its swarm-mates follow the frontier baseline during training
  - at evaluation time, every rover in the swarm runs its own independent
    copy of the SAME trained network (true decentralized execution: each
    copy only ever sees that one rover's own local knowledge + whatever
    it has received over the mesh network)

This is a legitimate and common way to bootstrap a decentralized
parameter-shared policy without full self-play, and it keeps training time
low enough to run on a laptop CPU.
"""
from __future__ import annotations

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from ..swarm_env import SwarmEnv, EnvConfig
from ..baselines.frontier import frontier_policy
from ..rover import N_ACTIONS, STAY_ACTION

PATCH_RADIUS = 5
PATCH_SIZE = 2 * PATCH_RADIUS + 1
OBS_DIM = PATCH_SIZE * PATCH_SIZE + 6  # patch + [battery, teammate_dx, teammate_dy, frontier_dx, frontier_dy, steps_frac]

# Training terrains are drawn from a seed pool that is disjoint from the
# seeds used for evaluation (evaluation uses seeds 0..n_seeds-1). Without
# this separation the policy would be tested on maps it had trained on.
TRAIN_SEED_MIN = 100_000
TRAIN_SEED_MAX = 1_000_000

COVERAGE_REWARD_SCALE = 50.0
INVALID_MOVE_PENALTY = -0.02
STEP_PENALTY = -0.001
DEATH_PENALTY = -1.0


def encode_observation(env: SwarmEnv, rover) -> np.ndarray:
    """Build the fixed-size egocentric observation a policy acts on: a
    local known/unknown/hazard patch plus a handful of scalar cues. This is
    exactly the information a real rover would have - its own sensed map
    and whatever peers have relayed to it - never global ground truth."""
    terrain = env.terrain
    patch = np.zeros((PATCH_SIZE, PATCH_SIZE), dtype=np.float32)
    for i in range(PATCH_SIZE):
        r = rover.row - PATCH_RADIUS + i
        for j in range(PATCH_SIZE):
            c = rover.col - PATCH_RADIUS + j
            if not (0 <= r < terrain.size and 0 <= c < terrain.size):
                patch[i, j] = 1.0  # treat off-map like a hazard: don't go there
            elif (r, c) not in rover.known:
                patch[i, j] = -1.0  # unknown
            elif terrain.hazard_mask[r, c]:
                patch[i, j] = 1.0  # known hazard
            else:
                patch[i, j] = 0.0  # known safe

    teammate_dx, teammate_dy, best_dist = 0.0, 0.0, None
    for other in env.rovers:
        if other.rover_id == rover.rover_id or not other.alive:
            continue
        dist = ((other.row - rover.row) ** 2 + (other.col - rover.col) ** 2) ** 0.5
        if dist <= rover.comm_radius and (best_dist is None or dist < best_dist):
            best_dist = dist
            span = max(rover.comm_radius, 1)
            teammate_dx = (other.row - rover.row) / span
            teammate_dy = (other.col - rover.col) / span

    frontier_dx, frontier_dy = 0.0, 0.0
    frontiers = rover.frontier_cells(terrain)
    if frontiers:
        target = min(frontiers, key=lambda cell: (cell[0] - rover.row) ** 2 + (cell[1] - rover.col) ** 2)
        span = max(terrain.size, 1)
        frontier_dx = (target[0] - rover.row) / span
        frontier_dy = (target[1] - rover.col) / span

    extra = np.array([
        rover.battery / 100.0,
        teammate_dx, teammate_dy,
        frontier_dx, frontier_dy,
        env.step_count / max(env.config.max_steps, 1),
    ], dtype=np.float32)
    return np.concatenate([patch.flatten(), extra])


class SingleRoverTrainingEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, env_config: EnvConfig | None = None, teammate_policy=frontier_policy):
        super().__init__()
        self.env_config = env_config or EnvConfig()
        self.teammate_policy = teammate_policy
        self.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(OBS_DIM,), dtype=np.float32)
        self.action_space = spaces.Discrete(N_ACTIONS)
        self.env: SwarmEnv | None = None
        self.learner_id: int = 0
        self._seed_rng = np.random.default_rng()

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            # `seed` seeds the terrain *sampler*, not the terrain itself, so
            # runs stay reproducible while still seeing many maps.
            self._seed_rng = np.random.default_rng(seed)
        # A fresh terrain every episode. Reusing one map (the behavior before
        # this was fixed) let the policy memorize a single layout instead of
        # learning a general exploration strategy.
        terrain_seed = int(self._seed_rng.integers(TRAIN_SEED_MIN, TRAIN_SEED_MAX))
        cfg = EnvConfig(**{**self.env_config.__dict__, "seed": terrain_seed})
        self.env = SwarmEnv(cfg)
        self.learner_id = self.env.rover_ids[0]
        learner = next(r for r in self.env.rovers if r.rover_id == self.learner_id)
        return encode_observation(self.env, learner), {}

    def step(self, action):
        env = self.env
        learner_before = next(r for r in env.rovers if r.rover_id == self.learner_id)
        prev_pos = learner_before.pos
        prev_known_count = len(learner_before.known)

        actions = {}
        for rid in env.rover_ids:
            actions[rid] = int(action) if rid == self.learner_id else self.teammate_policy(env, rid)
        env.step(actions)

        learner = next((r for r in env.rovers if r.rover_id == self.learner_id), None)
        reward = STEP_PENALTY
        terminated = False

        if learner is None or not learner.alive:
            reward += DEATH_PENALTY
            terminated = True
            obs = np.zeros(OBS_DIM, dtype=np.float32)
        else:
            new_cells = len(learner.known) - prev_known_count
            non_hazard_total = max(int((~env.terrain.hazard_mask).sum()), 1)
            reward += COVERAGE_REWARD_SCALE * (new_cells / non_hazard_total)
            if action != STAY_ACTION and learner.pos == prev_pos:
                reward += INVALID_MOVE_PENALTY
            obs = encode_observation(env, learner)

        truncated = bool(env.done) and not terminated
        return obs, reward, terminated, truncated, {}

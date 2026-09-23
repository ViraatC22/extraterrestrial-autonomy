"""Deployment-time wrapper around a trained PPO model.

Each rover that uses RLPolicy runs its own call to the same loaded network
- no shared state between rovers - which is what makes this a decentralized
policy at evaluation time even though training used a single learner.
"""
from __future__ import annotations

from pathlib import Path

from stable_baselines3 import PPO

from .policy_env import encode_observation


class RLPolicy:
    def __init__(self, model_path: str | Path):
        self.model_path = str(model_path)
        self.model = PPO.load(self.model_path, device="cpu")

    def __call__(self, env, rover_id: int) -> int:
        rover = next(r for r in env.rovers if r.rover_id == rover_id)
        obs = encode_observation(env, rover)
        action, _ = self.model.predict(obs, deterministic=True)
        return int(action)

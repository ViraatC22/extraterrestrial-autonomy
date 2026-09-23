"""Train the shared decentralized exploration policy with PPO.

Run from the project root (with the venv active):

    python -m exonaut.multiagent.rl.train --timesteps 300000

On a laptop CPU, ~300k timesteps takes roughly 20-40 minutes depending on
terrain size and rover count; a smaller --timesteps is fine for iterating.
The resulting model is saved to models/<out-name>.zip and is what
rl_policy.RLPolicy loads for evaluation/deployment.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import json

from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import SubprocVecEnv

from ..swarm_env import EnvConfig
from .policy_env import SingleRoverTrainingEnv

MODELS_DIR = Path(__file__).resolve().parents[4] / "models"


def train(
    total_timesteps: int = 500_000,
    n_envs: int = 8,
    n_rovers: int = 4,
    terrain_size: int = 48,
    comm_radius: int = 12,
    max_steps: int = 250,
    seed: int = 0,
    out_name: str = "ppo_lunar_swarm",
) -> Path:
    env_kwargs = dict(
        n_rovers=n_rovers, terrain_size=terrain_size,
        comm_radius=comm_radius, max_steps=max_steps, seed=seed,
    )

    def _make():
        return Monitor(SingleRoverTrainingEnv(EnvConfig(**env_kwargs)))

    # SubprocVecEnv runs each environment in its own process, so rollout
    # collection actually uses multiple cores (DummyVecEnv, the default,
    # steps them sequentially in one process).
    vec_env = make_vec_env(
        _make, n_envs=n_envs, seed=seed,
        vec_env_cls=SubprocVecEnv if n_envs > 1 else None,
    )
    model = PPO(
        "MlpPolicy", vec_env, verbose=1, n_steps=512, batch_size=512,
        gamma=0.995, learning_rate=3e-4, seed=seed,
        policy_kwargs=dict(net_arch=[128, 128]),
    )
    model.learn(total_timesteps=total_timesteps)

    MODELS_DIR.mkdir(exist_ok=True)
    out_path = MODELS_DIR / f"{out_name}.zip"
    model.save(str(out_path))

    # Record exactly what produced this checkpoint, so the training setup
    # reported in the paper can be traced back to the artifact.
    meta = {
        "total_timesteps": total_timesteps, "n_envs": n_envs, "seed": seed,
        "env": env_kwargs, "algorithm": "PPO", "policy": "MlpPolicy",
        "net_arch": [128, 128], "n_steps": 512, "batch_size": 512,
        "gamma": 0.995, "learning_rate": 3e-4,
        "teammate_policy_during_training": "frontier",
    }
    (MODELS_DIR / f"{out_name}_training_config.json").write_text(json.dumps(meta, indent=2))
    print(f"saved model to {out_path}")
    return out_path


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timesteps", type=int, default=500_000)
    parser.add_argument("--n-envs", type=int, default=8)
    parser.add_argument("--n-rovers", type=int, default=4)
    parser.add_argument("--terrain-size", type=int, default=48)
    parser.add_argument("--comm-radius", type=int, default=12)
    parser.add_argument("--max-steps", type=int, default=250)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out-name", type=str, default="ppo_lunar_swarm")
    args = parser.parse_args()
    train(
        total_timesteps=args.timesteps, n_envs=args.n_envs, n_rovers=args.n_rovers,
        terrain_size=args.terrain_size, comm_radius=args.comm_radius,
        max_steps=args.max_steps, seed=args.seed, out_name=args.out_name,
    )


if __name__ == "__main__":
    _cli()

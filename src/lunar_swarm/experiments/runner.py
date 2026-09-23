"""Batch experiment runner: sweeps algorithms x experimental conditions x
random seeds and records per-trial metrics to a CSV for statistical
comparison (see stats.py). This is what turns the simulator into an actual
science-fair experiment rather than a demo - every condition is run many
times on independently seeded terrain so differences between algorithms
can be tested for statistical significance, not eyeballed from one run.
"""
from __future__ import annotations

import itertools
from pathlib import Path

import pandas as pd

from ..environment import EnvConfig, SwarmEnv

RESULTS_DIR = Path(__file__).resolve().parents[3] / "data" / "results"


def _instantiate(policy_spec):
    """Baseline policies registered as classes (e.g. PheromonePolicy) hold
    per-trial state (a pheromone grid) and must be freshly instantiated for
    every trial. Plain functions and already-instantiated objects (e.g. a
    loaded RLPolicy, which is stateless per call) are reused as-is."""
    if isinstance(policy_spec, type):
        return policy_spec()
    return policy_spec


def run_trial(algorithm_name: str, policy_spec, env_kwargs: dict, seed: int) -> dict:
    cfg = EnvConfig(seed=seed, **env_kwargs)
    env = SwarmEnv(cfg)
    policy = _instantiate(policy_spec)
    while not env.done:
        actions = {rid: policy(env, rid) for rid in env.rover_ids}
        env.step(actions)
    metrics = env.metrics()
    metrics.pop("history", None)
    metrics.update({"algorithm": algorithm_name, "seed": seed, **env_kwargs})
    return metrics


def run_sweep(
    algorithms: dict,
    comm_radii: list[int],
    n_rovers_list: list[int],
    failure_rates: list[float],
    n_seeds: int = 10,
    base_kwargs: dict | None = None,
    save_as: str | None = "sweep_results.csv",
    progress_cb=None,
) -> pd.DataFrame:
    """algorithms: {name: policy_spec} where policy_spec is a callable
    policy(env, rover_id) -> action, or a class implementing that (fresh
    instance per trial)."""
    base_kwargs = base_kwargs or {}
    conditions = list(itertools.product(comm_radii, n_rovers_list, failure_rates))
    total = len(algorithms) * len(conditions) * n_seeds
    rows, done = [], 0

    for algo_name, policy_spec in algorithms.items():
        for comm_radius, n_rovers, failure_rate in conditions:
            for seed in range(n_seeds):
                env_kwargs = {
                    **base_kwargs, "comm_radius": comm_radius,
                    "n_rovers": n_rovers, "failure_rate": failure_rate,
                }
                rows.append(run_trial(algo_name, policy_spec, env_kwargs, seed))
                done += 1
                if progress_cb is not None:
                    progress_cb(done, total, algo_name, env_kwargs, seed)
                elif done % 25 == 0 or done == total:
                    print(f"[{done}/{total}] {algo_name} {env_kwargs} seed={seed}")

    df = pd.DataFrame(rows)
    if save_as:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = RESULTS_DIR / save_as
        df.to_csv(out_path, index=False)
        print(f"saved {len(df)} trial results to {out_path}")
    return df

"""Batch experiment runner.

Sweeps algorithms x experimental conditions x random seeds and records
per-trial outcomes to a CSV for statistical analysis (see stats.py).

Two design points that matter for the validity of the results:

1. **Matched terrain.** For a given (condition, seed), every algorithm is
   run on a bit-identical terrain, because terrain is generated purely from
   that seed. That makes the design a randomized block design and licenses
   the paired analyses in stats.py.

2. **Order/parallelism independence.** A trial is fully determined by
   (algorithm, condition, seed) with no shared mutable state, so running
   trials in parallel processes produces exactly the same numbers as
   running them serially. `test_runner.py` asserts this.

Policies are identified by short strings ("frontier", "rl:models/x.zip")
rather than by live objects so they can cross a process boundary; each
worker builds (and caches) its own policy instance.
"""
from __future__ import annotations

import itertools
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from ..baselines import BASELINES
from ..environment import EnvConfig, SwarmEnv

RESULTS_DIR = Path(__file__).resolve().parents[3] / "data" / "results"

# Per-process cache so a loaded torch model is reused across trials instead
# of being deserialized once per trial.
_POLICY_CACHE: dict[str, object] = {}


def build_policy(spec: str):
    """Construct a policy from its string spec.

    "frontier" | "potential_field" | "pheromone" -> classical baseline
    "rl:<path to .zip>"                          -> trained PPO policy

    Stateful baselines (pheromone keeps a decaying pheromone field) are
    rebuilt for every trial; stateless ones are cached.
    """
    if spec.startswith("rl:"):
        model_path = spec[3:]
        if spec not in _POLICY_CACHE:
            from ..rl.rl_policy import RLPolicy  # deferred: heavy torch import
            _POLICY_CACHE[spec] = RLPolicy(model_path)
        return _POLICY_CACHE[spec]

    if spec not in BASELINES:
        raise ValueError(f"unknown policy spec: {spec!r}")
    entry = BASELINES[spec]
    return entry() if isinstance(entry, type) else entry


def run_trial(algorithm: str, env_kwargs: dict, seed: int) -> dict:
    """Run one complete episode and return its outcome measures."""
    env = SwarmEnv(EnvConfig(seed=seed, **env_kwargs))
    policy = build_policy(algorithm)
    while not env.done:
        actions = {rid: policy(env, rid) for rid in env.rover_ids}
        env.step(actions)
    metrics = env.metrics()
    metrics.pop("history", None)
    metrics.update({"algorithm": algorithm, "seed": seed, **env_kwargs})
    return metrics


def _run_trial_star(args):
    return run_trial(*args)


def run_sweep(
    algorithms: list[str],
    comm_radii: list[int],
    n_rovers_list: list[int],
    failure_rates: list[float],
    n_seeds: int = 30,
    base_kwargs: dict | None = None,
    save_as: str | None = "sweep_results.csv",
    progress_cb=None,
    n_workers: int | None = None,
) -> pd.DataFrame:
    base_kwargs = base_kwargs or {}
    conditions = list(itertools.product(comm_radii, n_rovers_list, failure_rates))

    jobs = []
    for algorithm in algorithms:
        for comm_radius, n_rovers, failure_rate in conditions:
            for seed in range(n_seeds):
                env_kwargs = {
                    **base_kwargs, "comm_radius": comm_radius,
                    "n_rovers": n_rovers, "failure_rate": failure_rate,
                }
                jobs.append((algorithm, env_kwargs, seed))

    total = len(jobs)
    if n_workers is None:
        n_workers = max(1, (os.cpu_count() or 2) - 1)

    rows = []
    if n_workers == 1:
        for done, job in enumerate(jobs, start=1):
            rows.append(_run_trial_star(job))
            if progress_cb:
                progress_cb(done, total, job[0], job[1], job[2])
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futures = {pool.submit(_run_trial_star, job): job for job in jobs}
            for done, future in enumerate(as_completed(futures), start=1):
                rows.append(future.result())
                if progress_cb:
                    job = futures[future]
                    progress_cb(done, total, job[0], job[1], job[2])
                elif done % 100 == 0 or done == total:
                    print(f"[{done}/{total}] trials complete")

    df = pd.DataFrame(rows)
    # Deterministic row order regardless of completion order, so the saved
    # CSV is byte-stable across runs.
    sort_cols = [c for c in ["algorithm", "comm_radius", "n_rovers", "failure_rate", "seed"] if c in df.columns]
    df = df.sort_values(sort_cols).reset_index(drop=True)

    if save_as:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = RESULTS_DIR / save_as
        df.to_csv(out_path, index=False)
        print(f"saved {len(df)} trial results to {out_path}")
    return df

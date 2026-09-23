"""Convenience CLI for running the project's default experiment sweep
without going through the Streamlit UI - useful for regenerating
data/results/sweep_results.csv from a plain terminal (e.g. in CI or before
a fair, to refresh the numbers on the board).

    python scripts/run_default_sweep.py
"""
from __future__ import annotations

from lunar_swarm.algorithms import build_algorithm_registry
from lunar_swarm.experiments.runner import run_sweep


def main() -> None:
    registry = build_algorithm_registry()
    df = run_sweep(
        algorithms=registry,
        comm_radii=[6, 16, 40],
        n_rovers_list=[4],
        failure_rates=[0.0, 0.25],
        n_seeds=15,
        base_kwargs=dict(terrain_size=48, max_steps=250),
        save_as="sweep_results.csv",
    )
    print(df.groupby("algorithm")["final_coverage"].agg(["mean", "std"]))


if __name__ == "__main__":
    main()

"""Run the exact experiments reported in the paper.

Two sweeps:

  main_sweep.csv        every algorithm x communication radius x failure
                        rate, at the fixed swarm size used for training.
                        This is the sweep the hypothesis is tested on.

  swarm_size_sweep.csv  every algorithm x swarm size, at fixed
                        communication radius and no induced failures. This
                        is a secondary sweep checking whether conclusions
                        hold as the swarm grows beyond the size the RL
                        policy trained with.

Evaluation terrain seeds are 0..N-1. The RL policies were trained on
terrain seeds drawn from [100000, 1000000) (see rl/policy_env.py), so no
evaluation terrain was ever seen during training.

    python scripts/run_paper_experiments.py
"""
from __future__ import annotations

import time

from lunar_swarm.algorithms import available_algorithm_specs
from lunar_swarm.experiments.runner import run_sweep

# Held fixed across the main sweep; matches the RL training configuration
# so no algorithm is evaluated outside the regime it was built for.
TERRAIN_SIZE = 48
MAX_STEPS = 250
TRAINED_SWARM_SIZE = 4

COMM_RADII = [3, 6, 12, 24, 48]
FAILURE_RATES = [0.0, 0.25, 0.5]
SWARM_SIZES = [2, 4, 6, 8]
N_SEEDS = 30


def main() -> None:
    algorithms = available_algorithm_specs()
    print("algorithms under test:")
    for a in algorithms:
        print("  -", a)

    start = time.time()
    main_df = run_sweep(
        algorithms=algorithms,
        comm_radii=COMM_RADII,
        n_rovers_list=[TRAINED_SWARM_SIZE],
        failure_rates=FAILURE_RATES,
        n_seeds=N_SEEDS,
        base_kwargs=dict(terrain_size=TERRAIN_SIZE, max_steps=MAX_STEPS),
        save_as="main_sweep.csv",
    )
    print(f"main sweep: {len(main_df)} trials in {time.time() - start:.0f}s")

    start = time.time()
    swarm_df = run_sweep(
        algorithms=algorithms,
        comm_radii=[12],
        n_rovers_list=SWARM_SIZES,
        failure_rates=[0.0],
        n_seeds=N_SEEDS,
        base_kwargs=dict(terrain_size=TERRAIN_SIZE, max_steps=MAX_STEPS),
        save_as="swarm_size_sweep.csv",
    )
    print(f"swarm-size sweep: {len(swarm_df)} trials in {time.time() - start:.0f}s")


if __name__ == "__main__":
    main()

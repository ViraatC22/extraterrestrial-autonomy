"""Reproducibility guarantees for the experiment runner.

The paper's results are only meaningful if a trial is fully determined by
(algorithm, condition, seed). These tests assert that directly.
"""
import pandas as pd

from lunar_swarm.experiments.runner import run_sweep, run_trial

BASE = dict(terrain_size=32, max_steps=60)


def test_trial_is_deterministic_given_seed():
    kwargs = dict(BASE, comm_radius=10, n_rovers=3, failure_rate=0.0)
    a = run_trial("frontier", kwargs, seed=5)
    b = run_trial("frontier", kwargs, seed=5)
    assert a["final_coverage"] == b["final_coverage"]
    assert a["energy_spent"] == b["energy_spent"]
    assert a["steps_taken"] == b["steps_taken"]


def test_different_seeds_give_different_terrain_outcomes():
    kwargs = dict(BASE, comm_radius=10, n_rovers=3, failure_rate=0.0)
    results = {run_trial("frontier", kwargs, seed=s)["final_coverage"] for s in range(5)}
    assert len(results) > 1


def test_all_algorithms_see_identical_terrain_for_a_given_seed():
    """The basis for the paired/blocked statistical analysis."""
    from lunar_swarm.environment import EnvConfig, SwarmEnv

    envs = [SwarmEnv(EnvConfig(seed=7, terrain_size=32, n_rovers=3)) for _ in range(3)]
    reference = envs[0].terrain
    for env in envs[1:]:
        assert (env.terrain.elevation == reference.elevation).all()
        assert (env.terrain.hazard_mask == reference.hazard_mask).all()
        assert [r.pos for r in env.rovers] == [r.pos for r in envs[0].rovers]


def test_parallel_and_serial_sweeps_agree_exactly():
    """Parallelism must not change any reported number."""
    args = dict(
        algorithms=["frontier", "pheromone"],
        comm_radii=[6], n_rovers_list=[3], failure_rates=[0.0],
        n_seeds=4, base_kwargs=BASE, save_as=None,
    )
    serial = run_sweep(**args, n_workers=1)
    parallel = run_sweep(**args, n_workers=4)

    key = ["algorithm", "seed"]
    serial = serial.sort_values(key).reset_index(drop=True)
    parallel = parallel.sort_values(key).reset_index(drop=True)
    for col in ["final_coverage", "energy_spent", "steps_taken", "rovers_alive"]:
        pd.testing.assert_series_equal(serial[col], parallel[col], check_names=False)


def test_stateful_pheromone_policy_does_not_leak_between_trials():
    """PheromonePolicy holds a decaying pheromone grid; if it were shared
    across trials, trial N would be contaminated by trial N-1."""
    kwargs = dict(BASE, comm_radius=10, n_rovers=3, failure_rate=0.0)
    first = run_trial("pheromone", kwargs, seed=3)["final_coverage"]
    run_trial("pheromone", kwargs, seed=99)
    again = run_trial("pheromone", kwargs, seed=3)["final_coverage"]
    assert first == again

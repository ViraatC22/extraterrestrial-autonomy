import pandas as pd

from exonaut.experiments.mission_runner import (
    ExperimentCondition,
    run_mission_sweep,
    run_mission_trial,
)

FAST = {"size": 24, "n_targets": 2, "max_steps": 50}
MOON = ExperimentCondition("moon_test", "test", "moon")


def test_trial_records_condition_and_frozen_seed():
    row = run_mission_trial("astar", MOON, 300000, FAST)
    assert row["condition"] == "moon_test"
    assert row["split"] == "test"
    assert row["seed"] == 300000
    assert row["body"] == "moon"


def test_sweep_is_matched_and_deterministic():
    kwargs = dict(
        planners=("astar", "risk_aware_astar"),
        conditions=(MOON,),
        n_seeds=2,
        base_config=FAST,
        save_as=None,
        n_workers=1,
    )
    a = run_mission_sweep(**kwargs)
    b = run_mission_sweep(**kwargs)
    pd.testing.assert_frame_equal(a, b)
    assert set(a.groupby("seed")["planner"].nunique()) == {2}
    # Assert against the protocol rather than hardcoded numbers, so the test
    # follows the quarantine instead of pinning seeds that may be retired.
    from exonaut.experiments.protocol import load_splits

    expected = list(load_splits().get(MOON.split)[:2])
    assert sorted(a["seed"].unique().tolist()) == expected


def test_parallel_and_serial_sweeps_match():
    kwargs = dict(
        planners=("astar", "adaptive_risk_aware_astar"),
        conditions=(MOON,),
        n_seeds=2,
        base_config=FAST,
        save_as=None,
    )
    serial = run_mission_sweep(**kwargs, n_workers=1)
    parallel = run_mission_sweep(**kwargs, n_workers=2)
    pd.testing.assert_frame_equal(serial, parallel)

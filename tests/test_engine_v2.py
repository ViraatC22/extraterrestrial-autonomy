"""The v2 engine fixes, and the guarantee that v1 is untouched.

v1 must keep reproducing the committed confirmatory results, so every fix is
switched on only by engine="v2". scripts/verify_v1_reproduction.py checks all
750 committed missions; the test below checks a few quickly.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from exonaut.autonomy.priors import default_prior
from exonaut.autonomy.world_model import AdaptiveWorldModel
from exonaut.planners.base import Planner
from exonaut.robot import FaultSchedule
from exonaut.robot.vehicle import SlipRecord
from exonaut.simulation import MissionConfig, run_mission

RESULTS = Path(__file__).resolve().parents[1] / "data" / "results"
SMALL = {"body": "mars", "size": 40, "n_targets": 3, "max_steps": 300}


def test_default_engine_is_v1_and_reproduces_committed_rows():
    meta = json.loads((RESULTS / "exonaut_main.metadata.json").read_text())
    cond = {c["name"]: c for c in meta["conditions"]}
    rows = pd.read_csv(RESULTS / "exonaut_main.csv").sample(4, random_state=7)
    for _, row in rows.iterrows():
        c = cond[row["condition"]]
        config = MissionConfig(
            **{
                **meta["base_config"],
                "body": c["body"],
                "planner": row["planner"],
                "prior_body": c.get("prior_body", "moon"),
                **c.get("overrides", {}),
            }
        )
        assert config.engine == "v1"
        r = run_mission(config, seed=int(row["seed"]))
        assert r.termination == row["termination"]
        assert r.energy_spent == pytest.approx(row["energy_spent"], abs=1e-6)


def test_unknown_engine_is_rejected():
    with pytest.raises(ValueError):
        run_mission(MissionConfig(engine="v3", **SMALL), seed=200000)


def test_v2_calibrated_update_moves_less_on_one_reading():
    prior = default_prior("moon")
    kwargs = {"size": 16, "class_prior": prior["means"], "aleatoric_sd": prior["aleatoric_sd"]}
    old, new = AdaptiveWorldModel(**kwargs), AdaptiveWorldModel(**kwargs, calibrated_update=True)
    for wm in (old, new):
        wm.terrain_class[3, 3] = 2
        wm.observed[3, 3] = True
        wm.ingest_slip(SlipRecord(row=3, col=3, terrain_class=2, slope=0.0, slip=0.9, energy=1.0))
    start = prior["means"][2][0]
    moved_old = old.class_belief[2].mean - start
    moved_new = new.class_belief[2].mean - start
    assert 0 < moved_new < moved_old
    assert new.class_belief[2].variance > old.class_belief[2].variance


def test_v2_faults_are_scheduled_inside_the_window():
    config = MissionConfig(engine="v2", fault_rate=4.0, fault_window=50, **SMALL)
    seen = {}
    original = FaultSchedule.draw.__func__

    def spy(cls, rng, horizon, rate, allowed=None):
        seen["horizon"] = horizon
        return original(cls, rng, horizon, rate, allowed)

    FaultSchedule.draw = classmethod(spy)
    try:
        run_mission(config, seed=200001)
    finally:
        FaultSchedule.draw = classmethod(original)
    assert seen["horizon"] == 50


def test_v2_streams_isolate_faults_from_slip_draws():
    """With independent streams, adding faults changes nothing before the first
    fault fires. Under v1 the whole slip sequence shifted."""
    base = run_mission(
        MissionConfig(engine="v2", fault_rate=0.0, **SMALL), seed=200003, collect_history=True
    )
    faulted = run_mission(
        MissionConfig(engine="v2", fault_rate=3.0, **SMALL), seed=200003, collect_history=True
    )
    first_fault = next(
        (f["step"] for f in faulted.history if f["faults"]), faulted.history[-1]["step"] + 1
    )
    before = [(f["row"], f["col"], f["slip"]) for f in base.history if f["step"] < first_fault]
    before_faulted = [
        (f["row"], f["col"], f["slip"]) for f in faulted.history if f["step"] < first_fault
    ]
    assert before and before == before_faulted


def test_v2_intervention_relaxation_lasts_one_cycle():
    thresholds = []
    original = Planner.plan

    def spy(self, *args, **kwargs):
        thresholds.append(round(self.hazard_threshold, 2))
        return original(self, *args, **kwargs)

    Planner.plan = spy
    try:
        r = run_mission(
            MissionConfig(
                engine="v2",
                planner="risk_aware_astar",
                body="mars",
                size=48,
                n_targets=4,
                max_steps=500,
            ),
            seed=200007,
        )
    finally:
        Planner.plan = original
    assert max(thresholds) <= 0.65 + 1e-9, "relaxation ratcheted past one step"
    assert r.interventions < 50


def test_v2_removes_the_lander_livelock():
    """Validation seed 200007 livelocks under v1 (timeout at the lander after
    hundreds of help requests); v2 recharges instead of asking."""
    config = {
        "planner": "risk_aware_astar",
        "body": "mars",
        "size": 48,
        "n_targets": 4,
        "max_steps": 500,
    }
    v1 = run_mission(MissionConfig(**config), seed=200007)
    v2 = run_mission(MissionConfig(engine="v2", **config), seed=200007)
    assert v1.termination == "timeout" and v1.interventions > 100
    assert v2.interventions < v1.interventions / 10
    assert np.isfinite(v2.energy_spent)

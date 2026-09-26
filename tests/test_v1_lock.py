"""The v1 study is a historical record: its committed artifacts must not change.

`scripts/lock_v1_results.py` wrote a SHA-256 for every v1 artifact. If any of
them is edited, regenerated or replaced, these tests fail - which is the
point: v1 may be reinterpreted in writing, never silently rewritten.
"""

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "data" / "results" / "v1_LOCK.json"


@pytest.fixture(scope="module")
def lock():
    assert LOCK.exists(), "v1 lock missing: run scripts/lock_v1_results.py"
    return json.loads(LOCK.read_text())


def test_every_locked_v1_artifact_is_unchanged(lock):
    changed = [
        rel
        for rel, digest in lock["sha256"].items()
        if hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() != digest
    ]
    assert not changed, f"v1 artifacts changed since the lock: {changed}"


def test_lock_identifies_the_study(lock):
    from exonaut.experiments.protocol import verify_splits
    from exonaut.experiments.provenance import design_digest

    assert lock["engine_profile"] == "v1"
    assert lock["n_missions"] == len(pd.read_csv(ROOT / "data/results/exonaut_main.csv"))
    design = json.loads((ROOT / lock["design_config"]).read_text())
    assert design_digest(design) == lock["design_digest"]
    assert verify_splits()["checksum"] == lock["seed_split_checksum"]
    assert lock["reproduction"]["reproduced"] == lock["reproduction"]["missions"] == 750


def test_default_engine_is_still_v1():
    from exonaut.simulation import MissionConfig

    assert MissionConfig().engine == "v1"


def test_a_sample_of_committed_rows_reproduces():
    """A cheap in-suite check; the full 750 is scripts/verify_v1_reproduction.py."""
    from exonaut.simulation import MissionConfig, run_mission

    meta = json.loads((ROOT / "data/results/exonaut_main.metadata.json").read_text())
    conditions = {c["name"]: c for c in meta["conditions"]}
    rows = pd.read_csv(ROOT / "data/results/exonaut_main.csv")
    # every 125th row: spread across conditions and planners, deterministic
    for _, row in rows.iloc[::125].iterrows():
        cond = conditions[row["condition"]]
        config = MissionConfig(
            **{
                **meta["base_config"],
                "body": cond["body"],
                "planner": row["planner"],
                "prior_body": cond.get("prior_body", "moon"),
                **cond.get("overrides", {}),
            }
        )
        r = run_mission(config, seed=int(row["seed"]))
        assert r.termination == row["termination"]
        assert abs(r.science_return - row["science_return"]) < 1e-9
        assert abs(r.energy_spent - row["energy_spent"]) < 1e-6

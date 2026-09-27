"""The Study 2 runner and analysis do what the plan says, before any real data exist."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return load("run_study2")


@pytest.fixture(scope="module")
def analysis():
    return load("analyze_study2")


def test_confirmatory_run_refuses_without_a_frozen_plan(runner, monkeypatch, tmp_path):
    from exonaut.experiments import v2_protocol

    monkeypatch.setattr(v2_protocol, "PREREGISTRATION_V2", tmp_path / "missing.md")
    design = json.loads(runner.DESIGN.read_text())
    with pytest.raises(SystemExit, match="not frozen"):
        runner.check_authorized_run(design)


def test_dry_run_uses_validation_seeds_and_real_run_uses_the_manifest(runner):
    from exonaut.experiments.v2_protocol import load_manifest

    design = json.loads(runner.DESIGN.read_text())
    dry = runner.seeds_for(design, dry_run=True)
    assert all(200_000 <= s < 300_000 for seeds in dry.values() for s in seeds)
    real = runner.seeds_for(design, dry_run=False)  # seed numbers only; no terrain is built
    manifest = load_manifest()["splits"]
    assert real["mars"] == manifest["confirmatory_ood"][:230]
    assert real["moon"] == manifest["confirmatory_id"][:230]
    assert real["mars_faults"] == real["mars"]  # exploratory conditions share the Mars seeds


def test_design_matches_the_owner_decisions(runner):
    design = json.loads(runner.DESIGN.read_text())
    assert design["n_seeds"] == 230
    base = design["base_config"]
    assert base["engine"] == "v2" and base["class_assignment"] == "responsibility"
    assert base["epistemic_scale"] == 1.0
    roles = {c["name"]: c["role"] for c in design["conditions"]}
    assert roles == {
        "mars": "confirmatory",
        "moon": "secondary",
        "mars_high_uncertainty": "exploratory",
        "mars_faults": "exploratory",
    }
    assert not any("comm_delay" in c.get("overrides", {}) for c in design["conditions"])


def synthetic(n=60, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for cond, role in (
        ("mars", "confirmatory"),
        ("moon", "secondary"),
        ("mars_faults", "exploratory"),
    ):
        for s in range(n):
            for planner in ("risk_aware_astar", "adaptive_risk_aware_astar", "astar"):
                rows.append(
                    {
                        "condition": cond,
                        "role": role,
                        "planner": planner,
                        "seed": s,
                        "success": bool(rng.random() < 0.5),
                        "science_fraction": rng.random(),
                        "termination": "success",
                        "energy_spent": 1.0,
                        "severe_slip_events": 0,
                        "interventions": 0,
                        "calibration_records": 10,
                        "calibration_hits95": 7,
                        "severe_predicted_sum": 1.0,
                        "severe_observed": 1,
                        "prediction_steps": 50,
                    }
                )
    return pd.DataFrame(rows)


def test_analysis_structure_follows_the_plan(analysis):
    result = analysis.analyze(synthetic())
    p = result["primary"]
    assert p["condition"] == "mars" and p["metric"] == "success"
    assert p["test"].startswith("McNemar exact") and p["interval"] == "Newcombe hybrid score"
    assert [(r["condition"], r["metric"]) for r in result["secondary"]] == [
        ("mars", "science_fraction"),
        ("moon", "success"),
        ("moon", "science_fraction"),
    ]
    assert all("p_holm" in r for r in result["secondary"])
    assert all("p_value" not in r for r in result["exploratory"])


def test_primary_p_value_is_the_exact_binomial_on_discordant_pairs(analysis):
    from scipy import stats

    frame = synthetic(seed=3)
    p = analysis.analyze(frame)["primary"]
    expected = stats.binomtest(p["only_adaptive"], p["only_adaptive"] + p["only_fixed"], 0.5).pvalue
    assert p["p_value"] == pytest.approx(expected)

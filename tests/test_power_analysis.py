"""The sample-size calculation must use the same test the analysis will run."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def power():
    spec = importlib.util.spec_from_file_location(
        "power_analysis", ROOT / "scripts/power_analysis.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rejection_rule_matches_the_analysis_codes_binomtest(power):
    k = power.critical_counts(120)
    for d in range(1, 121):
        for w in range(d + 1):
            rejects = stats.binomtest(w, d, 0.5).pvalue <= power.ALPHA
            assert rejects == (k[d] >= 0 and min(w, d - w) <= k[d]), (d, w)


def test_exact_power_agrees_with_simulation(power):
    k = power.critical_counts(400)
    for n, delta, psi in ((200, 0.10, 0.30), (400, 0.075, 0.25)):
        exact = power.exact_power(n, delta, psi, k)
        simulated = power.simulated_power(n, delta, psi, sims=6000, seed=3)
        assert exact == pytest.approx(simulated, abs=0.02)


def test_power_is_alpha_at_no_effect_and_grows_with_n(power):
    k = power.critical_counts(600)
    assert power.exact_power(300, 0.0, 0.3, k) <= power.ALPHA + 1e-9  # exact test is conservative
    values = [power.exact_power(n, 0.10, 0.30, k) for n in (100, 200, 400, 600)]
    assert all(np.diff(values) > 0)


def test_impossible_effects_are_flagged(power):
    k = power.critical_counts(50)
    assert np.isnan(power.exact_power(50, 0.3, 0.2, k))  # delta cannot exceed discordance


def test_the_frozen_design_uses_the_n_the_sizing_rule_gives_on_the_final_engine(power):
    """study2.json's n must be the smallest n (steps of 10) that reaches the target."""
    import json

    sizing = json.loads(
        (ROOT / "data/validation/power_analysis/final_engine_sizing.json").read_text()
    )
    design = json.loads((ROOT / "experiments/configs/study2.json").read_text())
    assert design["n_seeds"] == sizing["n"]
    k = power.critical_counts(int(power.N_GRID.max()))
    at_n = power.exact_power(sizing["n"], power.MIN_EFFECT, sizing["psi_upper80"], k)
    below = power.exact_power(sizing["n"] - 10, power.MIN_EFFECT, sizing["psi_upper80"], k)
    assert at_n >= power.TARGET_POWER > below
    assert at_n == pytest.approx(sizing["exact_power_at_n"], abs=1e-12)

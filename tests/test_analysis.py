"""Validation of the confirmatory analysis routines.

These produce the paper's reported numbers, so they are checked against
reference implementations rather than trusted on inspection.
"""

import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.contingency_tables import mcnemar

from exonaut.experiments.analysis import (
    add_derived_columns,
    descriptive_table,
    generalization_gap,
    paired_binary,
    paired_continuous,
    primary_analysis,
)

TREAT = "adaptive_risk_aware_astar"
CTRL = "risk_aware_astar"


def _frame(treatment_success, control_success, treatment_sci=None, control_sci=None):
    n = len(treatment_success)
    treatment_sci = treatment_sci if treatment_sci is not None else [0.5] * n
    control_sci = control_sci if control_sci is not None else [0.5] * n
    rows = []
    for i in range(n):
        for planner, ok, sci in (
            (TREAT, treatment_success[i], treatment_sci[i]),
            (CTRL, control_success[i], control_sci[i]),
        ):
            rows.append(
                {
                    "condition": "c",
                    "seed": i,
                    "planner": planner,
                    "success": bool(ok),
                    "science_return": sci,
                    "science_possible": 1.0,
                    "energy_spent": 10.0,
                    "severe_slip_events": 0,
                    "interventions": 0,
                    "termination": "success" if ok else "energy_exhausted",
                }
            )
    return pd.DataFrame(rows)


def test_mcnemar_matches_statsmodels():
    rng = np.random.default_rng(0)
    a = rng.integers(0, 2, 40).astype(bool)
    b = rng.integers(0, 2, 40).astype(bool)
    df = add_derived_columns(_frame(a, b))
    mine = paired_binary(df, TREAT, CTRL, "c")

    n01 = int(np.count_nonzero(a & ~b))
    n10 = int(np.count_nonzero(~a & b))
    table = [[int(np.count_nonzero(a & b)), n01], [n10, int(np.count_nonzero(~a & ~b))]]
    ref = mcnemar(table, exact=True, correction=False)

    assert mine["n_discordant"] == n01 + n10
    assert mine["treatment_only_wins"] == n01
    assert np.isclose(mine["p_value"], ref.pvalue)


def test_mcnemar_no_discordant_pairs_is_null():
    a = [True, False, True, False]
    df = add_derived_columns(_frame(a, a))
    out = paired_binary(df, TREAT, CTRL, "c")
    assert out["n_discordant"] == 0
    assert out["p_value"] == 1.0
    assert out["mean_diff"] == 0.0


def test_mcnemar_detects_one_sided_advantage():
    # treatment succeeds on every seed the control fails, never the reverse
    control = [False] * 12 + [True] * 8
    treatment = [True] * 12 + [True] * 8
    df = add_derived_columns(_frame(treatment, control))
    out = paired_binary(df, TREAT, CTRL, "c")
    assert out["treatment_only_wins"] == 12
    assert out["control_only_wins"] == 0
    assert out["p_value"] < 0.001
    assert out["mean_diff"] == pytest.approx(0.6)


def test_paired_continuous_recovers_known_difference():
    rng = np.random.default_rng(3)
    block = rng.normal(0, 1.0, 30)  # large between-terrain variance
    control = 0.4 + block + rng.normal(0, 0.05, 30)
    treatment = control + 0.12 + rng.normal(0, 0.02, 30)
    df = add_derived_columns(_frame([True] * 30, [True] * 30, list(treatment), list(control)))
    out = paired_continuous(df, "science_fraction", TREAT, CTRL, "c")
    assert out["mean_diff"] == pytest.approx(0.12, abs=0.02)
    assert out["ci95_low"] < 0.12 < out["ci95_high"]
    assert out["p_value"] < 1e-6


def test_perfectly_consistent_difference_is_not_reported_as_null():
    """Zero variance in the paired differences makes a t-test undefined. A
    naive guard returns p = 1, which would hide a perfectly consistent
    effect; a sign test is the honest fallback."""
    control = [0.4] * 20
    treatment = [0.5] * 20
    df = add_derived_columns(_frame([True] * 20, [True] * 20, treatment, control))
    out = paired_continuous(df, "science_fraction", TREAT, CTRL, "c")
    assert out["mean_diff"] == pytest.approx(0.1)
    assert out["p_value"] < 1e-5

    same = add_derived_columns(_frame([True] * 20, [True] * 20, control, control))
    null = paired_continuous(same, "science_fraction", TREAT, CTRL, "c")
    assert null["mean_diff"] == 0.0
    assert null["p_value"] == 1.0


def test_primary_family_is_holm_corrected_and_monotonic():
    rng = np.random.default_rng(5)
    a = rng.integers(0, 2, 30).astype(bool)
    b = rng.integers(0, 2, 30).astype(bool)
    df = _frame(a, b)
    out = primary_analysis(df)
    assert not out.empty
    assert (out["family"] == "primary").all()
    assert (out["p_holm"] >= out["p_value"] - 1e-12).all()
    assert (out["p_holm"] <= 1.0).all()


def test_descriptive_and_gap_are_consistent_with_rows():
    df = _frame([True, True, False, False], [True, False, False, False])
    desc = descriptive_table(df)
    treat_row = desc[desc["planner"] == TREAT].iloc[0]
    assert treat_row["n"] == 4
    assert treat_row["success_rate"] == pytest.approx(0.5)

    two = pd.concat(
        [
            df.assign(condition="moon_id"),
            df.assign(condition="mars_ood", science_return=0.2),
        ]
    )
    gap = generalization_gap(two)
    assert set(gap["planner"]) == {TREAT, CTRL}
    for _, row in gap.iterrows():
        assert row["generalization_gap"] == pytest.approx(
            row["in_distribution"] - row["out_of_distribution"]
        )


def test_interval_table_wilson_matches_statsmodels():
    from statsmodels.stats.proportion import proportion_confint

    from exonaut.experiments.analysis import interval_table

    a = [True] * 7 + [False] * 13
    b = [True] * 12 + [False] * 8
    df = _frame(a, b, [0.1 * (i % 7) for i in range(20)], [0.05 * (i % 9) for i in range(20)])
    out = interval_table(df)
    for _, row in out.iterrows():
        lo, hi = proportion_confint(row["successes"], row["n"], alpha=0.05, method="wilson")
        assert np.isclose(row["success_ci_low"], lo) and np.isclose(row["success_ci_high"], hi)
        assert row["science_ci_low"] <= row["science_fraction"] <= row["science_ci_high"]


def test_paired_points_align_on_seed():
    from exonaut.experiments.analysis import paired_points

    df = _frame([True, False, True], [False, False, True], [0.3, 0.2, 0.9], [0.1, 0.2, 0.8])
    pts = paired_points(df)
    assert len(pts) == 3
    assert list(pts["science_treatment"]) == [0.3, 0.2, 0.9]
    assert list(pts["success_control"]) == [False, False, True]

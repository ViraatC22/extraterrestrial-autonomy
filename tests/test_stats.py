"""Validation of the statistical routines against reference implementations.

These are the numbers the paper reports, so the hand-written routines are
checked against statsmodels rather than trusted on inspection.
"""
import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.anova import AnovaRM
from statsmodels.stats.multitest import multipletests

from lunar_swarm.experiments.stats import (
    holm_bonferroni,
    paired_comparisons,
    repeated_measures_anova,
    summarize,
)


def _block_design(n_blocks=20, effects=(0.0, 0.7, 1.4), noise=0.5, seed=0):
    rng = np.random.default_rng(seed)
    block_effect = rng.normal(0, 1.0, n_blocks)
    rows = []
    for b in range(n_blocks):
        for idx, effect in enumerate(effects):
            rows.append({
                "algorithm": f"algo{idx}",
                "seed": b,
                "comm_radius": 10,
                "final_coverage": 5.0 + effect + block_effect[b] + rng.normal(0, noise),
            })
    return pd.DataFrame(rows)


def test_repeated_measures_anova_matches_statsmodels():
    df = _block_design()
    mine = repeated_measures_anova(df, "final_coverage")
    ref = AnovaRM(df, depvar="final_coverage", subject="seed", within=["algorithm"]).fit().anova_table
    assert np.isclose(mine["f_stat"], ref["F Value"].iloc[0])
    assert np.isclose(mine["p_value"], ref["Pr > F"].iloc[0])
    assert mine["df_treatment"] == int(ref["Num DF"].iloc[0])
    assert mine["df_error"] == int(ref["Den DF"].iloc[0])


@pytest.mark.parametrize(
    "p_values",
    [
        [0.001, 0.04, 0.03, 0.2, 0.7],
        [0.5, 0.5, 0.5],
        [0.0001, 0.0002],
        [0.049, 0.051],
    ],
)
def test_holm_bonferroni_matches_statsmodels(p_values):
    ref = multipletests(p_values, method="holm")[1]
    assert np.allclose(holm_bonferroni(p_values), ref)


def test_holm_bonferroni_is_monotonic_and_bounded():
    p_values = [0.01, 0.02, 0.03, 0.9]
    adjusted = holm_bonferroni(p_values)
    assert all(0.0 <= p <= 1.0 for p in adjusted)
    order = np.argsort(p_values)
    ordered = [adjusted[i] for i in order]
    assert ordered == sorted(ordered)


def test_paired_comparisons_detects_known_effect():
    df = _block_design(effects=(0.0, 1.5), noise=0.3, seed=1)
    out = paired_comparisons(df, "final_coverage")
    assert len(out) == 1
    row = out.iloc[0]
    # algo1 is 1.5 units above algo0 by construction
    assert np.isclose(row["mean_diff"], -1.5, atol=0.25)
    assert row["p_holm"] < 0.01
    assert row["ci95_low"] < row["mean_diff"] < row["ci95_high"]
    assert abs(row["cohens_dz"]) > 0.8  # large effect


def test_paired_comparisons_reports_null_when_no_effect():
    df = _block_design(effects=(0.0, 0.0), noise=0.5, seed=2)
    out = paired_comparisons(df, "final_coverage")
    assert out.iloc[0]["p_holm"] > 0.05
    assert not out.iloc[0]["significant"]


def test_pairing_beats_unpaired_when_block_variance_is_large():
    """The justification for using paired tests: with large between-terrain
    variance, an unpaired test can miss an effect that pairing detects."""
    from scipy import stats as sps

    df = _block_design(effects=(0.0, 0.4), noise=0.15, seed=3)
    paired_p = paired_comparisons(df, "final_coverage").iloc[0]["p_paired_t"]
    a = df[df["algorithm"] == "algo0"]["final_coverage"]
    b = df[df["algorithm"] == "algo1"]["final_coverage"]
    unpaired_p = sps.ttest_ind(a, b, equal_var=False).pvalue
    assert paired_p < unpaired_p


def test_summarize_ci_contains_mean():
    df = _block_design()
    out = summarize(df, "final_coverage")
    for _, row in out.iterrows():
        assert row["ci95_low"] <= row["mean"] <= row["ci95_high"]
        assert row["n"] == 20

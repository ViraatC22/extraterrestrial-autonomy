"""Statistical comparison utilities for experiment sweep results.

Kept deliberately simple (one-way ANOVA + pairwise Welch t-tests) so every
number on the science-fair board traces back to a standard, explainable
test rather than a black box.
"""
from __future__ import annotations

import pandas as pd
from scipy import stats


def summarize(df: pd.DataFrame, metric: str = "final_coverage", group_cols=("algorithm",)) -> pd.DataFrame:
    return df.groupby(list(group_cols))[metric].agg(["mean", "std", "count"]).reset_index()


def one_way_anova(df: pd.DataFrame, metric: str, group_col: str = "algorithm") -> dict:
    groups = [g[metric].values for _, g in df.groupby(group_col)]
    f_stat, p_value = stats.f_oneway(*groups)
    return {
        "metric": metric,
        "f_stat": float(f_stat),
        "p_value": float(p_value),
        "groups": sorted(df[group_col].unique().tolist()),
        "significant_p<0.05": bool(p_value < 0.05),
    }


def pairwise_ttests(df: pd.DataFrame, metric: str, group_col: str = "algorithm") -> pd.DataFrame:
    """Welch's t-test (does not assume equal variance) between every pair
    of algorithms on the given metric."""
    algos = sorted(df[group_col].unique())
    rows = []
    for i in range(len(algos)):
        for j in range(i + 1, len(algos)):
            a, b = algos[i], algos[j]
            va = df.loc[df[group_col] == a, metric]
            vb = df.loc[df[group_col] == b, metric]
            t_stat, p_value = stats.ttest_ind(va, vb, equal_var=False)
            rows.append({
                "algorithm_a": a, "algorithm_b": b,
                "mean_a": float(va.mean()), "mean_b": float(vb.mean()),
                "t_stat": float(t_stat), "p_value": float(p_value),
                "significant_p<0.05": bool(p_value < 0.05),
            })
    return pd.DataFrame(rows)

"""Statistical analysis of experiment sweep results.

Design note - why the tests here are *paired*: every algorithm is evaluated
on the same set of terrain seeds within each experimental condition, so a
trial is not an independent draw per algorithm; it is one block (a specific
terrain, a specific condition) observed under every algorithm. That is a
randomized block design, and the correct analysis matches observations
within a block instead of treating the groups as independent samples.
Pairing also removes between-terrain variance, which is large here because
some randomly generated maps are simply far more open than others.

Reported per comparison:
  - mean paired difference with a 95% confidence interval
  - paired t-test (parametric)
  - Wilcoxon signed-rank test (non-parametric companion, since coverage is
    a bounded proportion and need not be normally distributed)
  - Cohen's d_z (paired effect size)
  - Holm-Bonferroni adjusted p-values across the family of comparisons
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

# Columns that identify an experimental condition (everything except the
# algorithm, the random seed, and the measured outcomes).
CONDITION_COLS = [
    # EXONAUT single-rover experiment
    "condition",
    "body",
    "prior_body",
    "terrain_uncertainty",
    "fault_rate",
    "comm_delay",
    "sensor_noise_scale",
    "risk_budget",
    "size",
    "n_targets",
    # Historical multi-rover experiment
    "comm_radius",
    "n_rovers",
    "failure_rate",
    "terrain_size",
    # Shared
    "max_steps",
]


def _present_condition_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in CONDITION_COLS if c in df.columns]


def summarize(
    df: pd.DataFrame, metric: str = "final_coverage", group_cols=("algorithm",)
) -> pd.DataFrame:
    """Mean, SD, n, standard error and 95% CI (t-based) per group."""
    rows = []
    for key, g in df.groupby(list(group_cols)):
        values = g[metric].to_numpy(dtype=float)
        n = len(values)
        mean = float(values.mean())
        sd = float(values.std(ddof=1)) if n > 1 else 0.0
        se = sd / np.sqrt(n) if n > 0 else 0.0
        if n > 1:
            half = float(stats.t.ppf(0.975, n - 1) * se)
        else:
            half = 0.0
        key_tuple = key if isinstance(key, tuple) else (key,)
        row = dict(zip(group_cols, key_tuple, strict=False))
        row.update(
            {
                "mean": mean,
                "sd": sd,
                "n": n,
                "se": se,
                "ci95_low": mean - half,
                "ci95_high": mean + half,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(list(group_cols)).reset_index(drop=True)


def holm_bonferroni(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni step-down adjusted p-values.

    Controls the family-wise error rate while being uniformly more powerful
    than plain Bonferroni. Adjusted values are made monotonic and capped at
    1.0, so they can be compared directly against alpha.
    """
    m = len(p_values)
    if m == 0:
        return []
    order = np.argsort(p_values)
    adjusted = np.empty(m, dtype=float)
    running_max = 0.0
    for rank, idx in enumerate(order):
        value = (m - rank) * p_values[idx]
        running_max = max(running_max, value)  # enforce monotonicity
        adjusted[idx] = min(running_max, 1.0)
    return adjusted.tolist()


def paired_comparisons(
    df: pd.DataFrame,
    metric: str = "final_coverage",
    group_col: str = "algorithm",
    within: list[str] | None = None,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Pairwise paired comparisons between algorithms on matched blocks.

    `within` defaults to the experimental-condition columns plus `seed`, so
    algorithm A's trial on (comm_radius=6, seed=3) is compared against
    algorithm B's trial on exactly that same terrain and condition.
    """
    if within is None:
        within = _present_condition_cols(df) + (["seed"] if "seed" in df.columns else [])

    wide = df.pivot_table(index=within, columns=group_col, values=metric, aggfunc="mean")
    algos = sorted(c for c in wide.columns)

    rows = []
    for i in range(len(algos)):
        for j in range(i + 1, len(algos)):
            a, b = algos[i], algos[j]
            pair = wide[[a, b]].dropna()
            if len(pair) < 2:
                continue
            diff = (pair[a] - pair[b]).to_numpy(dtype=float)
            n = len(diff)
            mean_diff = float(diff.mean())
            sd_diff = float(diff.std(ddof=1))
            se_diff = sd_diff / np.sqrt(n)
            half = float(stats.t.ppf(1 - alpha / 2, n - 1) * se_diff) if n > 1 else 0.0

            if np.allclose(sd_diff, 0.0):
                # identical under both algorithms on every block
                t_stat, p_t = 0.0, 1.0
            else:
                t_stat, p_t = stats.ttest_rel(pair[a], pair[b])

            # Wilcoxon is undefined when every paired difference is zero.
            if np.allclose(diff, 0.0):
                w_stat, p_w = float("nan"), 1.0
            else:
                w_stat, p_w = stats.wilcoxon(pair[a], pair[b])

            cohens_dz = mean_diff / sd_diff if sd_diff > 0 else 0.0

            rows.append(
                {
                    "algorithm_a": a,
                    "algorithm_b": b,
                    "n_pairs": n,
                    "mean_a": float(pair[a].mean()),
                    "mean_b": float(pair[b].mean()),
                    "mean_diff": mean_diff,
                    "ci95_low": mean_diff - half,
                    "ci95_high": mean_diff + half,
                    "t_stat": float(t_stat),
                    "p_paired_t": float(p_t),
                    "wilcoxon_stat": float(w_stat),
                    "p_wilcoxon": float(p_w),
                    "cohens_dz": float(cohens_dz),
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["p_holm"] = holm_bonferroni(out["p_paired_t"].tolist())
    out["significant"] = out["p_holm"] < alpha
    return out.sort_values("p_holm").reset_index(drop=True)


def repeated_measures_anova(
    df: pd.DataFrame, metric: str = "final_coverage", group_col: str = "algorithm"
) -> dict:
    """One-way repeated-measures ANOVA across algorithms, blocking on the
    (condition, seed) pair. Equivalent to a randomized-block ANOVA: it
    partitions out between-block variance instead of letting it inflate the
    error term, which an independent one-way ANOVA would do here.
    """
    within = _present_condition_cols(df) + (["seed"] if "seed" in df.columns else [])
    wide = df.pivot_table(index=within, columns=group_col, values=metric, aggfunc="mean").dropna()
    if wide.shape[0] < 2 or wide.shape[1] < 2:
        return {"error": "need at least 2 blocks and 2 algorithms"}

    data = wide.to_numpy(dtype=float)
    n_blocks, k = data.shape
    grand = data.mean()
    ss_treat = n_blocks * ((data.mean(axis=0) - grand) ** 2).sum()
    ss_block = k * ((data.mean(axis=1) - grand) ** 2).sum()
    ss_total = ((data - grand) ** 2).sum()
    ss_error = ss_total - ss_treat - ss_block

    df_treat = k - 1
    df_error = (k - 1) * (n_blocks - 1)
    ms_treat = ss_treat / df_treat
    ms_error = ss_error / df_error
    f_stat = ms_treat / ms_error if ms_error > 0 else float("inf")
    p_value = float(stats.f.sf(f_stat, df_treat, df_error))
    # partial eta squared for the treatment effect
    partial_eta_sq = ss_treat / (ss_treat + ss_error) if (ss_treat + ss_error) > 0 else 0.0

    return {
        "metric": metric,
        "n_blocks": int(n_blocks),
        "k_algorithms": int(k),
        "f_stat": float(f_stat),
        "df_treatment": int(df_treat),
        "df_error": int(df_error),
        "p_value": p_value,
        "partial_eta_squared": float(partial_eta_sq),
        "significant": bool(p_value < 0.05),
        "algorithms": list(wide.columns),
    }


def two_way_anova(
    df: pd.DataFrame,
    metric: str = "final_coverage",
    factor_a: str = "algorithm",
    factor_b: str = "comm_radius",
) -> pd.DataFrame:
    """Factorial ANOVA with an interaction term.

    The interaction row is the one that tests the central hypothesis: if the
    advantage of one algorithm over another *changes* with communication
    radius, that shows up as a significant algorithm x comm_radius
    interaction, not as a main effect.
    """
    import statsmodels.api as sm
    from statsmodels.formula.api import ols

    work = df[[metric, factor_a, factor_b]].copy()
    work.columns = ["y", "fa", "fb"]
    model = ols("y ~ C(fa) * C(fb)", data=work).fit()
    table = sm.stats.anova_lm(model, typ=2)
    table = table.rename(
        index={
            "C(fa)": factor_a,
            "C(fb)": factor_b,
            "C(fa):C(fb)": f"{factor_a} x {factor_b} (interaction)",
        }
    )
    # partial eta^2 = SS_effect / (SS_effect + SS_residual)
    ss_resid = float(table.loc["Residual", "sum_sq"])
    table["partial_eta_sq"] = table["sum_sq"] / (table["sum_sq"] + ss_resid)
    table.loc["Residual", "partial_eta_sq"] = np.nan
    return table


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
def bootstrap_ci(
    values,
    statistic=np.mean,
    n_resamples: int = 10_000,
    alpha: float = 0.05,
    seed: int = 0,
    method: str = "bca",
) -> dict:
    """Bootstrap confidence interval for a statistic of one sample.

    Used where the t-interval's assumptions are uncomfortable: science
    fraction is a bounded ratio and mission success is a proportion, so
    neither is normally distributed, and for small samples a t-interval can
    extend past the range the quantity can physically take.

    `method="bca"` applies bias-correction and acceleration, which adjusts for
    skew in the bootstrap distribution; `method="percentile"` is the plain
    interval. BCa is the default because these outcomes are skewed near their
    bounds, which is exactly where the percentile interval misbehaves.
    """
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n < 2:
        point = float(statistic(values)) if n else float("nan")
        return {"statistic": point, "ci_low": point, "ci_high": point,
                "n": n, "n_resamples": 0, "method": method}

    rng = np.random.default_rng(seed)
    observed = float(statistic(values))
    idx = rng.integers(0, n, size=(n_resamples, n))
    replicates = np.array([statistic(values[row]) for row in idx], dtype=float)

    if method == "percentile":
        low, high = np.quantile(replicates, [alpha / 2, 1 - alpha / 2])
    elif method == "bca":
        # bias correction from the fraction of replicates below the observed
        proportion = float(np.mean(replicates < observed))
        proportion = min(max(proportion, 1e-9), 1 - 1e-9)
        z0 = stats.norm.ppf(proportion)
        # acceleration from jackknife skew
        jackknife = np.array(
            [statistic(np.delete(values, i)) for i in range(n)], dtype=float
        )
        deviations = jackknife.mean() - jackknife
        denominator = 6.0 * (np.sum(deviations**2) ** 1.5)
        acceleration = float(np.sum(deviations**3) / denominator) if denominator > 0 else 0.0

        z_alpha = stats.norm.ppf(alpha / 2)
        z_upper = stats.norm.ppf(1 - alpha / 2)

        def _adjust(z):
            return float(stats.norm.cdf(z0 + (z0 + z) / (1 - acceleration * (z0 + z))))

        low, high = np.quantile(replicates, [_adjust(z_alpha), _adjust(z_upper)])
    else:
        raise ValueError(f"unknown bootstrap method {method!r}")

    return {
        "statistic": observed,
        "ci_low": float(low),
        "ci_high": float(high),
        "n": n,
        "n_resamples": n_resamples,
        "method": method,
    }


def bootstrap_paired_difference(
    treatment,
    control,
    statistic=np.mean,
    n_resamples: int = 10_000,
    alpha: float = 0.05,
    seed: int = 0,
    method: str = "bca",
) -> dict:
    """Bootstrap CI for a paired difference, resampling *blocks*.

    Blocks are resampled rather than observations, because the experimental
    unit is one terrain seed observed under both planners. Resampling the two
    arms independently would destroy the pairing that the whole design exists
    to exploit, and would give an interval for the wrong quantity.
    """
    treatment = np.asarray(treatment, dtype=float)
    control = np.asarray(control, dtype=float)
    if len(treatment) != len(control):
        raise ValueError("paired bootstrap requires equal-length arms")
    result = bootstrap_ci(
        treatment - control, statistic=statistic,
        n_resamples=n_resamples, alpha=alpha, seed=seed, method=method,
    )
    result["mean_treatment"] = float(treatment.mean())
    result["mean_control"] = float(control.mean())
    # Two-sided bootstrap p-value: the smallest alpha at which the interval
    # would exclude zero, approximated from the replicate distribution.
    rng = np.random.default_rng(seed + 1)
    diff = treatment - control
    centred = diff - diff.mean()
    idx = rng.integers(0, len(diff), size=(n_resamples, len(diff)))
    null_replicates = np.array([statistic(centred[row]) for row in idx], dtype=float)
    observed = abs(float(statistic(diff)))
    result["p_bootstrap"] = float(
        (np.sum(np.abs(null_replicates) >= observed) + 1) / (n_resamples + 1)
    )
    return result

"""Confirmatory analysis for the EXONAUT mission experiment.

Implements exactly the analysis specified in docs/PREREGISTRATION.md, so the
reported numbers are produced by code rather than transcribed by hand.

Design: every planner is run on the same mission seeds within each condition,
so a trial is a matched block, not an independent draw. All contrasts are
therefore paired. Pairing also removes between-terrain variance, which is the
dominant noise source here - some randomly generated maps are simply far more
survivable than others.

Two outcome types, two tests:

* **Continuous** (science fraction): paired t-test, with a Wilcoxon
  signed-rank companion because a bounded ratio need not be normal, plus
  Cohen's d_z and a 95% CI on the mean paired difference.

* **Binary** (mission success): McNemar's exact test on the discordant pairs.
  A paired t-test on 0/1 data would be the wrong instrument; McNemar
  conditions on exactly the seeds where the two planners disagreed, which is
  where the information about a difference actually lives.

Holm-Bonferroni is applied across the prespecified primary family only.
Secondary contrasts are reported separately and labelled as such, so they
cannot inflate the primary family's error rate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .stats import bootstrap_paired_difference, holm_bonferroni

#: The proposed method and the control that isolates its single mechanism.
PRIMARY_TREATMENT = "adaptive_risk_aware_astar"
PRIMARY_CONTROL = "risk_aware_astar"
DISTANCE_CONTROL = "astar"

BLOCK_KEYS = ["condition", "seed"]


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add the outcome measures the plan is written in terms of."""
    out = df.copy()
    out["science_fraction"] = out["science_return"] / out["science_possible"]
    out["success"] = out["success"].astype(bool)
    # energy productivity: science actually returned per Wh expended
    out["science_per_energy"] = out["science_return"] / out["energy_spent"].clip(lower=1e-9)
    return out


def _paired_frames(
    df: pd.DataFrame, metric: str, treatment: str, control: str, condition: str | None = None
):
    """Align treatment and control on their shared blocks."""
    work = df if condition is None else df[df["condition"] == condition]
    pivot = work.pivot_table(index=BLOCK_KEYS, columns="planner", values=metric, aggfunc="mean")
    if treatment not in pivot.columns or control not in pivot.columns:
        return None
    pair = pivot[[treatment, control]].dropna()
    return pair if len(pair) else None


def paired_continuous(
    df: pd.DataFrame,
    metric: str,
    treatment: str,
    control: str,
    condition: str | None = None,
    alpha: float = 0.05,
    bootstrap: bool = True,
    n_resamples: int = 10_000,
    bootstrap_seed: int = 0,
) -> dict | None:
    pair = _paired_frames(df, metric, treatment, control, condition)
    if pair is None or len(pair) < 2:
        return None
    a = pair[treatment].to_numpy(float)
    b = pair[control].to_numpy(float)
    diff = a - b
    n = len(diff)
    mean_diff = float(diff.mean())
    sd_diff = float(diff.std(ddof=1))
    se = sd_diff / np.sqrt(n) if n else 0.0
    half = float(stats.t.ppf(1 - alpha / 2, n - 1) * se) if n > 1 else 0.0

    if sd_diff <= 1e-12:
        # Zero variance in the paired differences. A t-test is undefined here.
        # If every difference is also zero there is genuinely no effect; if
        # they are all the same non-zero value the effect is perfectly
        # consistent, and a sign test gives the honest p-value (2 * 0.5^n)
        # rather than the p = 1 a naive guard would report.
        if abs(mean_diff) <= 1e-12:
            t_stat, p_t = 0.0, 1.0
        else:
            t_stat = float("inf") * np.sign(mean_diff)
            p_t = float(min(1.0, 2.0 * 0.5**n))
    else:
        t_stat, p_t = stats.ttest_rel(a, b)
    if np.allclose(diff, 0.0):
        p_w = 1.0
    else:
        p_w = float(stats.wilcoxon(a, b).pvalue)

    row = {
        "condition": condition or "ALL",
        "metric": metric,
        "treatment": treatment,
        "control": control,
        "n_pairs": n,
        "mean_treatment": float(a.mean()),
        "mean_control": float(b.mean()),
        "mean_diff": mean_diff,
        "ci95_low": mean_diff - half,
        "ci95_high": mean_diff + half,
        "t_stat": float(t_stat),
        "p_value": float(p_t),
        "p_wilcoxon": p_w,
        "cohens_dz": float(mean_diff / sd_diff) if sd_diff > 0 else 0.0,
        "n_discordant": int(np.count_nonzero(np.abs(diff) > 1e-12)),
        "test": "paired t-test",
    }
    if bootstrap:
        # Science fraction is a bounded ratio, so the t-interval can extend
        # past values the quantity can physically take. The bootstrap interval
        # is reported alongside it as a distribution-free check; blocks are
        # resampled, preserving the pairing.
        boot = bootstrap_paired_difference(a, b, n_resamples=n_resamples, seed=bootstrap_seed)
        row["boot_ci_low"] = boot["ci_low"]
        row["boot_ci_high"] = boot["ci_high"]
        row["p_bootstrap"] = boot["p_bootstrap"]
    return row


def paired_binary(
    df: pd.DataFrame,
    treatment: str,
    control: str,
    condition: str | None = None,
    metric: str = "success",
    alpha: float = 0.05,
) -> dict | None:
    """McNemar's exact test on a paired binary outcome."""
    pair = _paired_frames(df, metric, treatment, control, condition)
    if pair is None:
        return None
    a = pair[treatment].to_numpy() > 0.5
    b = pair[control].to_numpy() > 0.5
    n = len(a)
    only_treatment = int(np.count_nonzero(a & ~b))  # treatment wins
    only_control = int(np.count_nonzero(~a & b))  # control wins
    discordant = only_treatment + only_control

    if discordant == 0:
        p_value = 1.0
    else:
        # Under H0 each discordant pair is a fair coin flip.
        p_value = float(stats.binomtest(only_treatment, discordant, 0.5).pvalue)

    diff = a.astype(float) - b.astype(float)
    mean_diff = float(diff.mean())
    sd = float(diff.std(ddof=1)) if n > 1 else 0.0
    se = sd / np.sqrt(n) if n else 0.0
    half = float(stats.t.ppf(1 - alpha / 2, n - 1) * se) if n > 1 else 0.0

    return {
        "condition": condition or "ALL",
        "metric": metric,
        "treatment": treatment,
        "control": control,
        "n_pairs": n,
        "mean_treatment": float(a.mean()),
        "mean_control": float(b.mean()),
        "mean_diff": mean_diff,
        "ci95_low": mean_diff - half,
        "ci95_high": mean_diff + half,
        "treatment_only_wins": only_treatment,
        "control_only_wins": only_control,
        "n_discordant": discordant,
        "p_value": p_value,
        "test": "McNemar exact",
    }


def primary_analysis(df: pd.DataFrame, alpha: float = 0.05) -> pd.DataFrame:
    """The prespecified primary family: adaptive vs fixed risk-aware, on
    science fraction and mission success, within each condition."""
    df = add_derived_columns(df)
    rows = []
    for condition in sorted(df["condition"].unique()):
        cont = paired_continuous(
            df, "science_fraction", PRIMARY_TREATMENT, PRIMARY_CONTROL, condition, alpha
        )
        if cont:
            rows.append(cont)
        binary = paired_binary(df, PRIMARY_TREATMENT, PRIMARY_CONTROL, condition, "success", alpha)
        if binary:
            rows.append(binary)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["p_holm"] = holm_bonferroni(out["p_value"].tolist())
    out["significant"] = out["p_holm"] < alpha
    out["family"] = "primary"
    return out


def secondary_analysis(df: pd.DataFrame, alpha: float = 0.05) -> pd.DataFrame:
    """Secondary contrasts against the distance-only control. Reported with
    their own Holm correction and never pooled into the primary family."""
    df = add_derived_columns(df)
    rows = []
    for condition in sorted(df["condition"].unique()):
        for treatment in (PRIMARY_CONTROL, PRIMARY_TREATMENT):
            cont = paired_continuous(
                df, "science_fraction", treatment, DISTANCE_CONTROL, condition, alpha
            )
            if cont:
                rows.append(cont)
            binary = paired_binary(df, treatment, DISTANCE_CONTROL, condition, "success", alpha)
            if binary:
                rows.append(binary)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["p_holm"] = holm_bonferroni(out["p_value"].tolist())
    out["significant"] = out["p_holm"] < alpha
    out["family"] = "secondary"
    return out


def descriptive_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per condition and planner: the outcome means a reader needs to
    interpret the contrasts, plus how each mission ended."""
    df = add_derived_columns(df)
    rows = []
    for (condition, planner), group in df.groupby(["condition", "planner"]):
        terminations = group["termination"].value_counts().to_dict()
        rows.append(
            {
                "condition": condition,
                "planner": planner,
                "n": len(group),
                "success_rate": float(group["success"].mean()),
                "science_fraction": float(group["science_fraction"].mean()),
                "science_fraction_sd": float(group["science_fraction"].std(ddof=1)),
                "energy_spent": float(group["energy_spent"].mean()),
                "severe_slip_events": float(group["severe_slip_events"].mean()),
                "interventions": float(group["interventions"].mean()),
                "immobilized": int(terminations.get("immobilized", 0)),
                "energy_exhausted": int(terminations.get("energy_exhausted", 0)),
                "timeout": int(terminations.get("timeout", 0)),
                "completed": int(terminations.get("success", 0)),
            }
        )
    return pd.DataFrame(rows).sort_values(["condition", "planner"]).reset_index(drop=True)


def generalization_gap(
    df: pd.DataFrame,
    in_condition: str = "moon_id",
    ood_condition: str = "mars_ood",
    metric: str = "science_fraction",
) -> pd.DataFrame:
    """G = M(in-distribution) - M(out-of-distribution), per planner.

    A smaller gap means performance transferred better. This is computed
    across different seed splits, so it is a between-condition descriptive
    contrast and is reported without a paired test.
    """
    df = add_derived_columns(df)
    rows = []
    for planner in sorted(df["planner"].unique()):
        inside = df[(df["condition"] == in_condition) & (df["planner"] == planner)][metric]
        outside = df[(df["condition"] == ood_condition) & (df["planner"] == planner)][metric]
        if inside.empty or outside.empty:
            continue
        rows.append(
            {
                "planner": planner,
                "metric": metric,
                "in_distribution": float(inside.mean()),
                "out_of_distribution": float(outside.mean()),
                "generalization_gap": float(inside.mean() - outside.mean()),
            }
        )
    return pd.DataFrame(rows)

"""The pre-specified Study 2 analysis. Nothing here may change after the freeze.

    python scripts/analyze_study2.py --dry-run    # on the validation dry run
    python scripts/analyze_study2.py              # on data/results/study2_main.csv

PRIMARY (one test, alpha 0.05, no multiplicity correction):
  Mars condition, adaptive vs fixed risk-aware A*, mission success, paired by
  seed: McNemar exact test, two-sided. Estimate: difference in success
  proportions with Newcombe's hybrid score 95% interval.

SECONDARY (Holm-corrected as one family of three):
  Mars science fraction: paired t-test, two-sided (Wilcoxon reported alongside).
  Moon mission success: McNemar exact, two-sided (Newcombe interval).
  Moon science fraction: paired t-test, two-sided (Wilcoxon alongside).

DESCRIPTIVE: termination mix, energy, severe slips, interventions, learner
calibration (95% class-mean coverage; predicted vs observed severe slip), and
distance-only A* as a reference. EXPLORATORY: every contrast in the
exploratory conditions, reported with intervals and without tests.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from exonaut.experiments.analysis import newcombe_paired_ci
from exonaut.experiments.stats import holm_bonferroni

ROOT = Path(__file__).resolve().parents[1]
TREATMENT, CONTROL = "adaptive_risk_aware_astar", "risk_aware_astar"
ALPHA = 0.05


def paired(frame: pd.DataFrame, condition: str, metric: str) -> pd.DataFrame:
    g = frame[frame.condition == condition].pivot_table(
        index="seed", columns="planner", values=metric
    )
    return g[[TREATMENT, CONTROL]].dropna()


def success_test(frame, condition) -> dict:
    g = paired(frame, condition, "success").astype(bool)
    a, b = g[TREATMENT].to_numpy(), g[CONTROL].to_numpy()
    only_a, only_b = int((a & ~b).sum()), int((~a & b).sum())
    p = 1.0 if only_a + only_b == 0 else float(stats.binomtest(only_a, only_a + only_b, 0.5).pvalue)
    d, lo, hi = newcombe_paired_ci(a, b)
    return {
        "condition": condition,
        "metric": "success",
        "test": "McNemar exact, two-sided",
        "n_pairs": len(g),
        "rate_adaptive": float(a.mean()),
        "rate_fixed": float(b.mean()),
        "difference": d,
        "ci95": [lo, hi],
        "interval": "Newcombe hybrid score",
        "only_adaptive": only_a,
        "only_fixed": only_b,
        "p_value": p,
    }


def science_test(frame, condition) -> dict:
    g = paired(frame, condition, "science_fraction")
    diff = (g[TREATMENT] - g[CONTROL]).to_numpy()
    n = len(diff)
    mean, sd = float(diff.mean()), float(diff.std(ddof=1))
    half = float(stats.t.ppf(0.975, n - 1) * sd / np.sqrt(n))
    t = stats.ttest_rel(g[TREATMENT], g[CONTROL])
    w = stats.wilcoxon(diff) if np.any(diff != 0) else None
    return {
        "condition": condition,
        "metric": "science_fraction",
        "test": "paired t, two-sided",
        "n_pairs": n,
        "mean_adaptive": float(g[TREATMENT].mean()),
        "mean_fixed": float(g[CONTROL].mean()),
        "difference": mean,
        "ci95": [mean - half, mean + half],
        "interval": "t",
        "p_value": float(t.pvalue),
        "p_wilcoxon": float(w.pvalue) if w is not None else 1.0,
    }


def descriptives(frame: pd.DataFrame) -> list[dict]:
    rows = []
    for (cond, planner), g in frame.groupby(["condition", "planner"]):
        rows.append(
            {
                "condition": cond,
                "planner": planner,
                "n": len(g),
                "success_rate": float(g.success.mean()),
                "science_fraction": float(g.science_fraction.mean()),
                "terminations": g.termination.value_counts().to_dict(),
                "energy_spent_mean": float(g.energy_spent.mean()),
                "severe_slip_events_mean": float(g.severe_slip_events.mean()),
                "interventions_mean": float(g.interventions.mean()),
                "calibration_coverage95": float(
                    g.calibration_hits95.sum() / max(g.calibration_records.sum(), 1)
                ),
                "severe_predicted_per_step": float(
                    g.severe_predicted_sum.sum() / max(g.prediction_steps.sum(), 1)
                ),
                "severe_observed_per_step": float(
                    g.severe_observed.sum() / max(g.prediction_steps.sum(), 1)
                ),
            }
        )
    return rows


def analyze(frame: pd.DataFrame) -> dict:
    primary = success_test(frame, "mars")
    primary["reject_h0"] = bool(primary["p_value"] <= ALPHA)
    secondary = [
        science_test(frame, "mars"),
        success_test(frame, "moon"),
        science_test(frame, "moon"),
    ]
    for row, p_holm in zip(
        secondary, holm_bonferroni([r["p_value"] for r in secondary]), strict=True
    ):
        row["p_holm"] = float(p_holm)
        row["reject_h0"] = bool(p_holm <= ALPHA)
    exploratory = []
    for cond in sorted(set(frame.condition) - {"mars", "moon"}):
        for row in (success_test(frame, cond), science_test(frame, cond)):
            row.pop("p_value", None)
            row.pop("p_wilcoxon", None)
            row["note"] = "exploratory: estimate and interval only, no test"
            exploratory.append(row)
    return {
        "primary": primary,
        "secondary": secondary,
        "exploratory": exploratory,
        "descriptive": descriptives(frame),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        source = ROOT / "data/validation/study2_dry_run/study2_dry_run.csv"
        out = ROOT / "data/validation/study2_dry_run/study2_dry_run_analysis.json"
    else:
        source = ROOT / "data/results/study2_main.csv"
        out = ROOT / "data/results/study2_analysis.json"
    result = analyze(pd.read_csv(source))
    result["source"] = str(source.relative_to(ROOT))
    out.write_text(json.dumps(result, indent=2, default=float) + "\n")
    print(json.dumps({"primary": result["primary"]}, indent=2, default=float))


if __name__ == "__main__":
    main()

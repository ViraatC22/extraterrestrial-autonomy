r"""Paper figures and macros for the calibration audit, from its raw artifacts.

Reads data/validation/calibration/ (written by scripts/calibration_study.py)
and writes paper/tables/exonaut_calibration_macros.tex and the figures
paper/figures/v2_calibration_*.pdf. Nothing is typed: every number the paper
quotes about calibration is a macro defined here from those files.

    python scripts/calibration_paper_assets.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "validation" / "calibration"
TABLES = ROOT / "paper" / "tables"
FIGURES = ROOT / "paper" / "figures"
METADATA = {".pdf": {"CreationDate": None, "ModDate": None}, ".png": {"Software": None}}

LEVEL_NAMES = {50: "Fifty", 80: "Eighty", 90: "Ninety", 95: "NinetyFive"}
BODY_NAMES = {"mars": "Mars", "moon": "Moon"}
CANDIDATE_NAMES = {
    "M1": "MOne",
    "M3": "MThree",
    "M2a": "MTwoA",
    "M4a": "MFourA",
    "M2b": "MTwoB",
    "M4b": "MFourB",
}
DIAGNOSTIC_NAMES = {
    "v2": "Base",
    "ablate_class": "NoMisclass",
    "ablate_dispersion": "TrueDispersion",
    "ablate_prior_mean": "TruePriorMean",
}
CLASS_LABELS = {0: "smooth", 1: "rocky", 2: "fines", 3: "bedrock", 4: "talus"}


def macro(name: str, value) -> str:
    return rf"\newcommand{{\{name}}}{{{value}}}"


def coverage_macros(prefix: str, cov: pd.DataFrame, names: dict) -> list[str]:
    lines = []
    for _, r in cov.iterrows():
        if r["variant"] not in names:
            continue
        stem = f"{prefix}{names[r['variant']]}{BODY_NAMES[r['body']]}"
        for level, word in LEVEL_NAMES.items():
            lines.append(macro(f"{stem}Cov{word}", f"{r[f'cov{level}']:.2f}"))
        lines.append(macro(f"{stem}CovNinetyFiveLo", f"{r['cov95_lo']:.2f}"))
        lines.append(macro(f"{stem}CovNinetyFiveHi", f"{r['cov95_hi']:.2f}"))
        lines.append(macro(f"{stem}MedianSd", f"{r['median_sd']:.3f}"))
        lines.append(macro(f"{stem}MedianError", f"{r['median_abs_error']:.3f}"))
        lines.append(macro(f"{stem}Missions", int(r["missions"])))
    return lines


def predictive_macros(prefix: str, pred: pd.DataFrame, names: dict) -> list[str]:
    lines = []
    for _, r in pred.iterrows():
        if r["variant"] not in names:
            continue
        stem = f"{prefix}{names[r['variant']]}{BODY_NAMES[r['body']]}"
        lines.append(macro(f"{stem}PredCovNinety", f"{r['pcov90']:.2f}"))
        lines.append(macro(f"{stem}SevereRate", f"{r['severe_rate']:.3f}"))
        lines.append(macro(f"{stem}MeanPSevere", f"{r['mean_p_severe']:.3f}"))
        lines.append(macro(f"{stem}Brier", f"{r['brier_severe']:.4f}"))
    return lines


def calibration_curve(
    cov: pd.DataFrame, order: list[str], path: Path, labels: dict | None = None
) -> None:
    labels = labels or {}
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.9), sharey=True)
    levels = [50, 80, 90, 95]
    for ax, body in zip(axes, ("mars", "moon"), strict=True):
        ax.plot([0.5, 0.95], [0.5, 0.95], color="grey", lw=0.8, ls="--", label="perfect")
        for name in order:
            row = cov[(cov.variant == name) & (cov.body == body)]
            if row.empty:
                continue
            r = row.iloc[0]
            ax.plot(
                [lv / 100 for lv in levels],
                [r[f"cov{lv}"] for lv in levels],
                marker="o",
                lw=1.2,
                label=labels.get(name, name),
            )
        ax.set_title(f"{body.capitalize()} (validation)", fontsize=10)
        ax.set_xlabel("nominal interval coverage")
        ax.set_xlim(0.45, 1.0)
        ax.set_ylim(0.0, 1.02)
    axes[0].set_ylabel("empirical coverage of the true class mean")
    axes[1].legend(fontsize=7, frameon=False, loc="lower right")
    fig.tight_layout()
    for suffix in (".pdf", ".png"):
        fig.savefig(path.with_suffix(suffix), dpi=160, metadata=METADATA[suffix])
    plt.close(fig)


def class_coverage(by_class: pd.DataFrame, variants: list[str], path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
    width = 0.8 / len(variants)
    for ax, body in zip(axes, ("mars", "moon"), strict=True):
        for i, name in enumerate(variants):
            g = by_class[(by_class.variant == name) & (by_class.body == body)].sort_values("cls")
            ax.bar(g.cls + (i - (len(variants) - 1) / 2) * width, g.cov95, width, label=name)
        ax.axhline(0.95, color="grey", lw=0.8, ls="--")
        ax.set_xticks(range(5), [CLASS_LABELS[k] for k in range(5)], fontsize=8)
        ax.set_title(f"{body.capitalize()} (validation)", fontsize=10)
        ax.set_ylim(0, 1.05)
    axes[0].set_ylabel("95% interval coverage")
    axes[1].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    for suffix in (".pdf", ".png"):
        fig.savefig(path.with_suffix(suffix), dpi=160, metadata=METADATA[suffix])
    plt.close(fig)


def write_markdown(cov, pred, by_class, selection, fit) -> None:
    """Generated results tables for docs/CALIBRATION_AUDIT.md (no typed numbers)."""
    out = [
        "<!-- AUTO-GENERATED by scripts/calibration_paper_assets.py. Do not edit. -->",
        "# Calibration: validation results (generated)",
        "",
        f"Status under the pre-specified rule: **{selection['status']}**. "
        f"Selected: {selection['selected'] or 'none'}. Best available (smallest maximum coverage "
        f"error on Mars): {selection['best_available_if_none_accepted'] or selection['selected']}.",
        "",
        "Fitted scales (TRAIN): " + ", ".join(f"{k} = {v:.2f}" for k, v in fit.items()),
        "",
        "## Class-mean interval coverage (validation seeds 200000-200099)",
        "",
        "| candidate | body | 50% | 80% | 90% | 95% [95% CI] | median sd | median abs. error |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in cov.sort_values(["variant", "body"]).iterrows():
        out.append(
            f"| {r.variant} | {r.body} | {r.cov50:.3f} | {r.cov80:.3f} | {r.cov90:.3f} | "
            f"{r.cov95:.3f} [{r.cov95_lo:.3f}, {r.cov95_hi:.3f}] | {r.median_sd:.3f} | "
            f"{r.median_abs_error:.3f} |"
        )
    out += [
        "",
        "## Acceptance checks",
        "",
        "| candidate | accepted | failed checks | max coverage error (Mars) |",
        "|---|---|---|---|",
    ]
    for name, v in selection["verdicts"].items():
        failed = ", ".join(k for k, ok in v["checks"].items() if not ok) or "-"
        out.append(f"| {name} | {v['accepted']} | {failed} | {v['mars_max_coverage_error']:.3f} |")
    out += [
        "",
        "## Per-step predictive calibration and severe-slip prediction",
        "",
        "Behaviour differs between candidates, so severe-slip rates (and Brier scores) are not",
        "comparable across rows; compare mean predicted P(severe) with the observed rate within a row.",
        "",
        "| candidate | body | steps | predictive 90% coverage | observed severe rate | mean predicted P(severe) | Brier |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, r in pred.sort_values(["variant", "body"]).iterrows():
        out.append(
            f"| {r.variant} | {r.body} | {int(r.steps)} | {r.pcov90:.3f} | {r.severe_rate:.4f} | "
            f"{r.mean_p_severe:.4f} | {r.brier_severe:.4f} |"
        )
    out += [
        "",
        "## 95% coverage by terrain class",
        "",
        "| candidate | body | " + " | ".join(CLASS_LABELS.values()) + " |",
        "|---|---|" + "---|" * 5,
    ]
    for (name, body), g in by_class.groupby(["variant", "body"]):
        vals = {int(r.cls): r.cov95 for _, r in g.iterrows()}
        out.append(
            f"| {name} | {body} | "
            + " | ".join(f"{vals.get(k, float('nan')):.2f}" for k in range(5))
            + " |"
        )
    (DATA / "RESULTS.md").write_text("\n".join(out) + "\n")


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    lines = [
        "% AUTO-GENERATED by scripts/calibration_paper_assets.py from data/validation/calibration/.",
        "% Train and validation seeds only. Not confirmatory.",
    ]
    diag_cov = pd.read_csv(DATA / "diagnose_coverage.csv")
    diag_pred = pd.read_csv(DATA / "diagnose_predictive.csv")
    lines += coverage_macros("CalDiag", diag_cov, DIAGNOSTIC_NAMES)
    lines += predictive_macros("CalDiag", diag_pred, DIAGNOSTIC_NAMES)
    summary = json.loads((DATA / "summary.json").read_text())
    for body, share in summary["diagnose"]["misclassified_reading_share"].items():
        lines.append(macro(f"CalMisclassShare{BODY_NAMES[body]}", f"{100 * share:.1f}"))
    fit = json.loads((DATA / "fit.json").read_text())
    for key, word in (
        ("M2_scale_fit_on_mars", "CalScaleMTwoMars"),
        ("M2_scale_fit_on_moon", "CalScaleMTwoMoon"),
        ("M4_scale_fit_on_mars", "CalScaleMFourMars"),
        ("M4_scale_fit_on_moon", "CalScaleMFourMoon"),
    ):
        lines.append(macro(word, f"{fit[key]:.2f}"))

    evaluated = (DATA / "evaluate_coverage.csv").exists()
    lines.append(macro("CalEvaluated", "yes" if evaluated else "no"))
    if evaluated:
        cov = pd.read_csv(DATA / "evaluate_coverage.csv")
        pred = pd.read_csv(DATA / "evaluate_predictive.csv")
        by_class = pd.read_csv(DATA / "evaluate_coverage_by_class.csv")
        selection = json.loads((DATA / "selection.json").read_text())
        lines += coverage_macros("Cal", cov, CANDIDATE_NAMES)
        lines += predictive_macros("Cal", pred, CANDIDATE_NAMES)
        lines.append(macro("CalStatus", selection["status"]))
        lines.append(macro("CalSelected", selection["selected"] or "none"))
        best = selection["selected"] or selection["best_available_if_none_accepted"]
        lines.append(macro("CalBestAvailable", best))
        accepted = [n for n, v in selection["verdicts"].items() if v["accepted"]]
        lines.append(macro("CalAcceptedCount", len(accepted)))
        order = list(CANDIDATE_NAMES)
        labels = {}
        if fit["M4_scale_fit_on_moon"] == 1.0:
            # a fitted scale of exactly 1 makes M4a the same method as M3
            order.remove("M4a")
            labels["M3"] = "M3 (= M4a: fitted scale 1.00)"
        calibration_curve(cov, order, FIGURES / "v2_calibration_curve", labels)
        class_coverage(
            by_class,
            ["M1", "M3", best] if best not in ("M1", "M3") else ["M1", "M3"],
            FIGURES / "v2_calibration_by_class",
        )
        # the bedrock class, the audit's clearest failure
        for name in ("M1", "M3"):
            for body in ("mars", "moon"):
                row = by_class[
                    (by_class.variant == name) & (by_class.body == body) & (by_class.cls == 3)
                ]
                if len(row):
                    lines.append(
                        macro(
                            f"Cal{CANDIDATE_NAMES[name]}{BODY_NAMES[body]}BedrockCov",
                            f"{row.iloc[0].cov95:.2f}",
                        )
                    )
                row = by_class[
                    (by_class.variant == name) & (by_class.body == body) & (by_class.cls == 2)
                ]
                if len(row):
                    lines.append(
                        macro(
                            f"Cal{CANDIDATE_NAMES[name]}{BODY_NAMES[body]}FinesCov",
                            f"{row.iloc[0].cov95:.2f}",
                        )
                    )
    (TABLES / "exonaut_calibration_macros.tex").write_text("\n".join(lines) + "\n")
    if evaluated:
        write_markdown(cov, pred, by_class, selection, fit)
    print(f"wrote {len(lines) - 2} calibration macros")


if __name__ == "__main__":
    main()

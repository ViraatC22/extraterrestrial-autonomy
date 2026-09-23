r"""Generate every number, table, and figure the EXONAUT paper reports.

Nothing in the paper is typed by hand. The paper \input{}s the files this
script writes, so a reported value can only change if the underlying
row-level CSV changes. Running this script is therefore the single point at
which results enter the write-up.

    python scripts/make_exonaut_paper_assets.py                # confirmatory
    python scripts/make_exonaut_paper_assets.py --pilot        # pilot only

Provenance: the macro file records the source CSV, its row count, the git
commit recorded in the run's metadata sidecar, and the seed splits used.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from exonaut.experiments.analysis import (
    add_derived_columns,
    descriptive_table,
    generalization_gap,
    primary_analysis,
    secondary_analysis,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "data" / "results"
TABLE_DIR = PROJECT_ROOT / "paper" / "tables"
FIGURE_DIR = PROJECT_ROOT / "paper" / "figures"

PLANNER_LABELS = {
    "astar": "Distance-only A*",
    "risk_aware_astar": "Fixed risk-aware A*",
    "adaptive_risk_aware_astar": "Adaptive risk-aware A*",
}
PLANNER_SHORT = {
    "astar": "Astar",
    "risk_aware_astar": "Fixed",
    "adaptive_risk_aware_astar": "Adaptive",
}
CONDITION_LABELS = {
    "moon_id": "Moon (in-distribution)",
    "mars_ood": "Mars (OOD)",
    "mars_high_uncertainty": "Mars, 1.5x slip dispersion",
    "mars_faults": "Mars, fault injection",
    "mars_comm_delay": "Mars, 20-step intervention delay",
}
CONDITION_SHORT = {
    "moon_id": "MoonID",
    "mars_ood": "MarsOOD",
    "mars_high_uncertainty": "MarsUnc",
    "mars_faults": "MarsFault",
    "mars_comm_delay": "MarsComm",
}
CONDITION_ORDER = list(CONDITION_LABELS)


def _tex_escape(text: str) -> str:
    return str(text).replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")


def _fmt_p(p: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "--"
    if p < 0.001:
        return "$<$0.001"
    return f"{p:.3f}"


def _ordered_conditions(df: pd.DataFrame) -> list[str]:
    present = set(df["condition"].unique())
    ordered = [c for c in CONDITION_ORDER if c in present]
    return ordered + sorted(present - set(ordered))


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------
def write_descriptive_table(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    desc = descriptive_table(df)
    lines = [
        r"\begin{tabular}{@{}llrrrrr@{}}",
        r"\toprule",
        r"Condition & Planner & $n$ & Success & Science frac. & Immob. & Energy out \\",
        r"\midrule",
    ]
    for condition in _ordered_conditions(df):
        block = desc[desc["condition"] == condition]
        for i, (_, row) in enumerate(block.iterrows()):
            label = _tex_escape(CONDITION_LABELS.get(condition, condition)) if i == 0 else ""
            lines.append(
                f"{label} & {_tex_escape(PLANNER_LABELS.get(row['planner'], row['planner']))} "
                f"& {int(row['n'])} & {row['success_rate']:.2f} "
                f"& {row['science_fraction']:.3f} "
                f"& {int(row['immobilized'])} & {int(row['energy_exhausted'])} \\\\"
            )
        lines.append(r"\addlinespace")
    lines += [r"\bottomrule", r"\end{tabular}"]
    path.write_text("\n".join(lines) + "\n")
    return desc


def write_contrast_table(results: pd.DataFrame, path: Path, caption_metric: str) -> None:
    lines = [
        r"\begin{tabular}{@{}llr@{~}lll@{}}",
        r"\toprule",
        r"Condition & Outcome & $\Delta$ & 95\% CI & Test & $p_{\mathrm{Holm}}$ \\",
        r"\midrule",
    ]
    for _, row in results.iterrows():
        metric = "Science fraction" if row["metric"] == "science_fraction" else "Mission success"
        star = r"$^{*}$" if row.get("significant") else ""
        lines.append(
            f"{_tex_escape(CONDITION_LABELS.get(row['condition'], row['condition']))} "
            f"& {metric} & {row['mean_diff']:+.3f} "
            f"& [{row['ci95_low']:+.3f}, {row['ci95_high']:+.3f}] "
            f"& {_tex_escape(row['test'])} & {_fmt_p(row['p_holm'])}{star} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    path.write_text("\n".join(lines) + "\n")


def write_gap_table(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    gap = generalization_gap(df)
    lines = [
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Planner & In-distribution & Out-of-distribution & Gap $G$ \\",
        r"\midrule",
    ]
    for _, row in gap.iterrows():
        lines.append(
            f"{_tex_escape(PLANNER_LABELS.get(row['planner'], row['planner']))} "
            f"& {row['in_distribution']:.3f} & {row['out_of_distribution']:.3f} "
            f"& {row['generalization_gap']:.3f} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    path.write_text("\n".join(lines) + "\n")
    return gap


# --------------------------------------------------------------------------
# figures
# --------------------------------------------------------------------------
def write_outcome_figure(df: pd.DataFrame, stem: Path) -> None:
    desc = descriptive_table(df)
    conditions = _ordered_conditions(df)
    planners = [p for p in PLANNER_LABELS if p in set(df["planner"])]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    width = 0.8 / max(len(planners), 1)
    x = np.arange(len(conditions))

    for metric, ax, title in (
        ("success_rate", axes[0], "Mission success rate"),
        ("science_fraction", axes[1], "Science fraction returned"),
    ):
        for i, planner in enumerate(planners):
            values = [
                float(desc[(desc["condition"] == c) & (desc["planner"] == planner)][metric].iloc[0])
                if not desc[(desc["condition"] == c) & (desc["planner"] == planner)].empty else np.nan
                for c in conditions
            ]
            ax.bar(x + i * width - 0.4 + width / 2, values, width,
                   label=PLANNER_LABELS[planner])
        ax.set_xticks(x)
        ax.set_xticklabels([CONDITION_LABELS.get(c, c).replace(", ", ",\n")
                            for c in conditions], fontsize=7)
        ax.set_title(title)
        ax.set_ylim(0, 1.0)
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    for suffix in (".pdf", ".png"):
        fig.savefig(stem.with_suffix(suffix), dpi=180)
    plt.close(fig)


def write_termination_figure(df: pd.DataFrame, stem: Path) -> None:
    """How missions ended - the mechanism behind the headline numbers."""
    work = add_derived_columns(df)
    conditions = _ordered_conditions(work)
    planners = [p for p in PLANNER_LABELS if p in set(work["planner"])]
    reasons = ["success", "energy_exhausted", "immobilized", "timeout"]
    colors = {"success": "#2a9d8f", "energy_exhausted": "#e9c46a",
              "immobilized": "#e76f51", "timeout": "#8d99ae"}

    fig, axes = plt.subplots(1, len(conditions), figsize=(3.0 * len(conditions), 3.6),
                             sharey=True)
    if len(conditions) == 1:
        axes = [axes]
    for ax, condition in zip(axes, conditions):
        bottoms = np.zeros(len(planners))
        for reason in reasons:
            counts = []
            for planner in planners:
                sub = work[(work["condition"] == condition) & (work["planner"] == planner)]
                counts.append(float((sub["termination"] == reason).sum()) / max(len(sub), 1))
            ax.bar(range(len(planners)), counts, bottom=bottoms, label=reason,
                   color=colors.get(reason))
            bottoms += np.array(counts)
        ax.set_xticks(range(len(planners)))
        ax.set_xticklabels([PLANNER_SHORT[p] for p in planners], fontsize=7, rotation=20)
        ax.set_title(CONDITION_LABELS.get(condition, condition).replace(", ", ",\n"),
                     fontsize=8)
        ax.set_ylim(0, 1)
    axes[0].set_ylabel("fraction of missions")
    axes[-1].legend(fontsize=6, loc="lower right")
    fig.tight_layout()
    for suffix in (".pdf", ".png"):
        fig.savefig(stem.with_suffix(suffix), dpi=180)
    plt.close(fig)


# --------------------------------------------------------------------------
# macros
# --------------------------------------------------------------------------
def write_macros(df: pd.DataFrame, desc: pd.DataFrame, primary: pd.DataFrame,
                 gap: pd.DataFrame, csv_path: Path, prefix: str, path: Path) -> None:
    meta_path = csv_path.with_suffix(".metadata.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    git = meta.get("git", {}) or {}

    lines = [
        f"% AUTO-GENERATED by scripts/make_exonaut_paper_assets.py from {csv_path.name}",
        "% Do not edit by hand. Regenerate instead.",
        rf"\newcommand{{\{prefix}Missions}}{{{len(df)}}}",
        rf"\newcommand{{\{prefix}Conditions}}{{{df['condition'].nunique()}}}",
        rf"\newcommand{{\{prefix}Planners}}{{{df['planner'].nunique()}}}",
        rf"\newcommand{{\{prefix}SeedsPerCondition}}{{{meta.get('n_seeds_per_condition', 'n/a')}}}",
        rf"\newcommand{{\{prefix}Commit}}{{{_tex_escape((git.get('commit') or 'unknown')[:12])}}}",
        rf"\newcommand{{\{prefix}SplitChecksum}}{{{_tex_escape((meta.get('seed_split_checksum') or 'unknown')[:12])}}}",
    ]

    for _, row in desc.iterrows():
        key = f"{CONDITION_SHORT.get(row['condition'], row['condition'])}{PLANNER_SHORT.get(row['planner'], row['planner'])}"
        lines.append(rf"\newcommand{{\{prefix}{key}Success}}{{{row['success_rate']:.2f}}}")
        lines.append(rf"\newcommand{{\{prefix}{key}Science}}{{{row['science_fraction']:.3f}}}")
        lines.append(rf"\newcommand{{\{prefix}{key}Immob}}{{{int(row['immobilized'])}}}")
        lines.append(rf"\newcommand{{\{prefix}{key}EnergyOut}}{{{int(row['energy_exhausted'])}}}")
        lines.append(rf"\newcommand{{\{prefix}{key}Interventions}}{{{row['interventions']:.1f}}}")
        lines.append(rf"\newcommand{{\{prefix}{key}SlipEvents}}{{{row['severe_slip_events']:.2f}}}")

    for _, row in primary.iterrows():
        key = CONDITION_SHORT.get(row["condition"], row["condition"])
        metric = "Science" if row["metric"] == "science_fraction" else "Success"
        lines.append(rf"\newcommand{{\{prefix}Delta{key}{metric}}}{{{row['mean_diff']:+.3f}}}")
        lines.append(rf"\newcommand{{\{prefix}P{key}{metric}}}{{{_fmt_p(row['p_holm'])}}}")

    for _, row in gap.iterrows():
        key = PLANNER_SHORT.get(row["planner"], row["planner"])
        lines.append(rf"\newcommand{{\{prefix}Gap{key}}}{{{row['generalization_gap']:.3f}}}")

    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()

    csv_path = args.csv or RESULTS_DIR / (
        "exonaut_pilot.csv" if args.pilot else "exonaut_main.csv")
    if not csv_path.exists():
        raise SystemExit(f"{csv_path} not found - run the experiment first.")
    prefix = "Pilot" if args.pilot else "Main"

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(csv_path)

    tag = "pilot" if args.pilot else "main"
    desc = write_descriptive_table(df, TABLE_DIR / f"exonaut_{tag}_descriptive.tex")
    gap = write_gap_table(df, TABLE_DIR / f"exonaut_{tag}_gap.tex")

    primary = primary_analysis(df)
    secondary = secondary_analysis(df)
    if not primary.empty:
        write_contrast_table(primary, TABLE_DIR / f"exonaut_{tag}_primary.tex",
                             "primary")
        primary.to_csv(RESULTS_DIR / f"exonaut_{tag}_primary.csv", index=False)
    if not secondary.empty:
        write_contrast_table(secondary, TABLE_DIR / f"exonaut_{tag}_secondary.tex",
                             "secondary")
        secondary.to_csv(RESULTS_DIR / f"exonaut_{tag}_secondary.csv", index=False)

    write_outcome_figure(df, FIGURE_DIR / f"exonaut_{tag}_outcomes")
    write_termination_figure(df, FIGURE_DIR / f"exonaut_{tag}_terminations")
    write_macros(df, desc, primary, gap, csv_path, prefix,
                 TABLE_DIR / f"exonaut_{tag}_macros.tex")

    print(f"generated assets from {csv_path.name} ({len(df)} rows)")
    if not primary.empty:
        print("\nPRIMARY (adaptive vs fixed risk-aware):")
        for _, r in primary.iterrows():
            flag = " *" if r["significant"] else ""
            print(f"  {r['condition']:22s} {r['metric']:17s} "
                  f"d={r['mean_diff']:+.3f} [{r['ci95_low']:+.3f},{r['ci95_high']:+.3f}] "
                  f"p_holm={r['p_holm']:.4f}{flag}")
    if not gap.empty:
        print("\nGENERALIZATION GAP (science fraction, Moon ID -> Mars OOD):")
        for _, r in gap.iterrows():
            print(f"  {r['planner']:26s} {r['in_distribution']:.3f} -> "
                  f"{r['out_of_distribution']:.3f}   G={r['generalization_gap']:.3f}")


if __name__ == "__main__":
    main()

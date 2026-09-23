"""Generate every number and figure that appears in the paper.

Nothing in paper/paper.tex is typed by hand: this script reads the results
CSVs and emits LaTeX tables into paper/tables/ and figures into
paper/figures/, which the paper \\input{}s and \\includegraphics{}es. It
also writes paper/tables/generated_macros.tex, defining LaTeX macros for
the in-line numbers quoted in the prose (sample sizes, headline means,
test statistics), so the running text cannot drift from the data either.

Run after a sweep:
    python scripts/make_paper_assets.py
"""
from __future__ import annotations

import json
import platform
import subprocess
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lunar_swarm.experiments.stats import (
    paired_comparisons,
    repeated_measures_anova,
    summarize,
    two_way_anova,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "data" / "results"
PAPER_DIR = PROJECT_ROOT / "paper"
TABLES_DIR = PAPER_DIR / "tables"
FIGURES_DIR = PAPER_DIR / "figures"

MAIN_CSV = RESULTS_DIR / "main_sweep.csv"
SWARM_CSV = RESULTS_DIR / "swarm_size_sweep.csv"

# Consistent ordering/labels/colors across every table and figure.
ALGO_ORDER = ["frontier", "potential_field", "pheromone", "rl"]
ALGO_LABELS = {
    "frontier": "Frontier",
    "potential_field": "Potential field",
    "pheromone": "Pheromone",
    "rl": "RL (PPO)",
}
ALGO_COLORS = {
    "frontier": "#4C72B0",
    "potential_field": "#DD8452",
    "pheromone": "#55A868",
    "rl": "#C44E52",
}
METRIC_LABELS = {
    "final_coverage": "Final coverage (fraction of traversable cells)",
    "coverage_per_energy": "Coverage per unit energy",
    "energy_spent": "Energy spent (battery units)",
    "rovers_alive": "Rovers surviving",
}


# --------------------------------------------------------------------------
# data loading
# --------------------------------------------------------------------------
def collapse_rl_seeds(df: pd.DataFrame) -> pd.DataFrame:
    """Average the independently-trained RL policies into a single 'rl'
    condition per block.

    Three policies were trained from different RL seeds; treating them as
    three separate algorithms would let RL occupy three of four slots in
    every comparison and would confound 'which algorithm' with 'which
    training run'. Averaging them per block gives one RL observation per
    block whose value is the expected performance of a policy produced by
    this training procedure - which is the quantity the hypothesis is
    actually about. Per-seed spread is reported separately.
    """
    out = df.copy()
    out["training_seed"] = out["algorithm"].str.extract(r"ppo_seed(\d+)")[0]
    out["algorithm"] = out["algorithm"].where(
        ~out["algorithm"].str.startswith("rl:"), "rl"
    )
    block_cols = [c for c in ["comm_radius", "n_rovers", "failure_rate",
                              "terrain_size", "max_steps", "seed"] if c in out.columns]
    numeric = ["final_coverage", "coverage_per_energy", "energy_spent",
               "rovers_alive", "steps_taken", "n_rovers"]
    numeric = [c for c in numeric if c in out.columns]
    agg = out.groupby(block_cols + ["algorithm"], as_index=False)[numeric].mean()
    return agg


def fmt_p(p: float) -> str:
    """Format a p-value for publication."""
    if p < 1e-4:
        return r"$<10^{-4}$"
    if p < 0.001:
        return f"{p:.1e}".replace("e-0", r"\times 10^{-").replace("e-", r"\times 10^{-") + "}$"
    return f"{p:.3f}"


def _p_plain(p: float) -> str:
    if p < 1e-4:
        return "<0.0001"
    return f"{p:.4f}"


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------
def table_descriptive(df: pd.DataFrame, metric: str, path: Path, caption: str, label: str):
    s = summarize(df, metric=metric, group_cols=("algorithm",))
    s = s.set_index("algorithm").reindex([a for a in ALGO_ORDER if a in set(s["algorithm"])])
    lines = [
        r"\begin{table}[t]", r"\centering",
        r"\caption{" + caption + "}", r"\label{" + label + "}",
        r"\begin{tabular}{lrrrr}", r"\toprule",
        r"Algorithm & Mean & SD & 95\% CI & $n$ \\", r"\midrule",
    ]
    for algo, row in s.iterrows():
        lines.append(
            f"{ALGO_LABELS.get(algo, algo)} & {row['mean']:.4f} & {row['sd']:.4f} & "
            f"[{row['ci95_low']:.4f}, {row['ci95_high']:.4f}] & {int(row['n'])} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""]
    path.write_text("\n".join(lines))


def table_paired(df: pd.DataFrame, metric: str, path: Path, caption: str, label: str):
    pc = paired_comparisons(df, metric=metric)
    lines = [
        r"\begin{table}[t]", r"\centering",
        r"\caption{" + caption + "}", r"\label{" + label + "}",
        r"\small",
        r"\begin{tabular}{llrrrrr}", r"\toprule",
        r"A & B & $\Delta$ (A$-$B) & 95\% CI & $t$ & $p_{\mathrm{Holm}}$ & $d_z$ \\",
        r"\midrule",
    ]
    for _, r in pc.iterrows():
        a = ALGO_LABELS.get(r["algorithm_a"], r["algorithm_a"])
        b = ALGO_LABELS.get(r["algorithm_b"], r["algorithm_b"])
        star = r"$^{*}$" if r["significant"] else ""
        lines.append(
            f"{a} & {b} & {r['mean_diff']:+.4f}{star} & "
            f"[{r['ci95_low']:+.4f}, {r['ci95_high']:+.4f}] & {r['t_stat']:.2f} & "
            f"{_p_plain(r['p_holm'])} & {r['cohens_dz']:+.2f} \\\\"
        )
    lines += [
        r"\bottomrule", r"\end{tabular}",
        r"\par\vspace{2pt}\footnotesize $^{*}$significant at $\alpha=0.05$ after "
        r"Holm--Bonferroni correction across all " + str(len(pc)) + r" comparisons. "
        r"$n=" + str(int(pc['n_pairs'].iloc[0])) + r"$ matched blocks per comparison.",
        r"\end{table}", "",
    ]
    path.write_text("\n".join(lines))
    return pc


def table_two_way(df: pd.DataFrame, metric: str, path: Path, caption: str, label: str):
    table = two_way_anova(df, metric=metric)
    lines = [
        r"\begin{table}[t]", r"\centering",
        r"\caption{" + caption + "}", r"\label{" + label + "}",
        r"\begin{tabular}{lrrrrr}", r"\toprule",
        r"Source & SS & df & $F$ & $p$ & $\eta^2_p$ \\", r"\midrule",
    ]
    for source, row in table.iterrows():
        name = source.replace("_", r"\_").replace(" x ", r" $\times$ ")
        f_val = "--" if pd.isna(row.get("F")) else f"{row['F']:.2f}"
        p_val = "--" if pd.isna(row.get("PR(>F)")) else _p_plain(row["PR(>F)"])
        eta = "--" if pd.isna(row.get("partial_eta_sq")) else f"{row['partial_eta_sq']:.3f}"
        lines.append(
            f"{name} & {row['sum_sq']:.4f} & {int(row['df'])} & {f_val} & {p_val} & {eta} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""]
    path.write_text("\n".join(lines))
    return table


def table_by_condition(df: pd.DataFrame, metric: str, condition: str, path: Path,
                       caption: str, label: str):
    s = summarize(df, metric=metric, group_cols=("algorithm", condition))
    pivot_mean = s.pivot(index=condition, columns="algorithm", values="mean")
    pivot_sd = s.pivot(index=condition, columns="algorithm", values="sd")
    algos = [a for a in ALGO_ORDER if a in pivot_mean.columns]

    header = " & ".join(ALGO_LABELS.get(a, a) for a in algos)
    lines = [
        r"\begin{table}[t]", r"\centering",
        r"\caption{" + caption + "}", r"\label{" + label + "}",
        r"\begin{tabular}{l" + "r" * len(algos) + "}", r"\toprule",
        condition.replace("_", r"\_") + " & " + header + r" \\", r"\midrule",
    ]
    for idx in pivot_mean.index:
        cells = " & ".join(
            f"{pivot_mean.loc[idx, a]:.3f} ({pivot_sd.loc[idx, a]:.3f})" for a in algos
        )
        lines.append(f"{idx} & {cells} \\\\")
    lines += [
        r"\bottomrule", r"\end{tabular}",
        r"\par\vspace{2pt}\footnotesize Cell entries are mean (SD).",
        r"\end{table}", "",
    ]
    path.write_text("\n".join(lines))


def table_rl_seed_spread(raw: pd.DataFrame, path: Path, caption: str, label: str):
    rl = raw[raw["algorithm"].str.startswith("rl:")].copy()
    if rl.empty:
        path.write_text("% no RL runs found\n")
        return
    rl["training_seed"] = rl["algorithm"].str.extract(r"ppo_seed(\d+)")[0]
    lines = [
        r"\begin{table}[t]", r"\centering",
        r"\caption{" + caption + "}", r"\label{" + label + "}",
        r"\begin{tabular}{lrrr}", r"\toprule",
        r"Training seed & Mean coverage & SD & $n$ trials \\", r"\midrule",
    ]
    for seed, g in rl.groupby("training_seed"):
        lines.append(
            f"{seed} & {g['final_coverage'].mean():.4f} & "
            f"{g['final_coverage'].std(ddof=1):.4f} & {len(g)} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""]
    path.write_text("\n".join(lines))


# --------------------------------------------------------------------------
# figures
# --------------------------------------------------------------------------
def _style():
    plt.rcParams.update({
        "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
        "figure.dpi": 150, "savefig.bbox": "tight",
    })


def figure_metric_vs_comm(df: pd.DataFrame, metric: str, path: Path, ylabel: str):
    _style()
    fig, ax = plt.subplots(figsize=(4.2, 3.0))
    for algo in ALGO_ORDER:
        sub = df[df["algorithm"] == algo]
        if sub.empty:
            continue
        s = summarize(sub, metric=metric, group_cols=("comm_radius",))
        ax.errorbar(
            s["comm_radius"], s["mean"],
            yerr=[s["mean"] - s["ci95_low"], s["ci95_high"] - s["mean"]],
            marker="o", markersize=4, capsize=3, linewidth=1.5,
            label=ALGO_LABELS[algo], color=ALGO_COLORS[algo],
        )
    ax.set_xlabel("Communication radius $R_c$ (cells)")
    ax.set_ylabel(ylabel)
    ax.set_xscale("log")
    ax.set_xticks(sorted(df["comm_radius"].unique()))
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.legend(frameon=False, fontsize=7)
    fig.savefig(path)
    plt.close(fig)


def figure_metric_vs_failure(df: pd.DataFrame, metric: str, path: Path, ylabel: str):
    _style()
    fig, ax = plt.subplots(figsize=(4.2, 3.0))
    rates = sorted(df["failure_rate"].unique())
    width = 0.8 / max(len(ALGO_ORDER), 1)
    for i, algo in enumerate(ALGO_ORDER):
        sub = df[df["algorithm"] == algo]
        if sub.empty:
            continue
        s = summarize(sub, metric=metric, group_cols=("failure_rate",))
        x = np.arange(len(rates)) + i * width - 0.4 + width / 2
        ax.bar(x, s["mean"], width=width, label=ALGO_LABELS[algo],
               color=ALGO_COLORS[algo],
               yerr=[s["mean"] - s["ci95_low"], s["ci95_high"] - s["mean"]],
               capsize=2, error_kw={"linewidth": 0.8})
    ax.set_xticks(np.arange(len(rates)))
    ax.set_xticklabels([f"{r:.0%}" for r in rates])
    ax.set_xlabel("Fraction of swarm disabled at mid-mission")
    ax.set_ylabel(ylabel)
    ax.legend(frameon=False, fontsize=7)
    fig.savefig(path)
    plt.close(fig)


def figure_swarm_size(df: pd.DataFrame, path: Path):
    _style()
    fig, ax = plt.subplots(figsize=(4.2, 3.0))
    for algo in ALGO_ORDER:
        sub = df[df["algorithm"] == algo]
        if sub.empty:
            continue
        s = summarize(sub, metric="final_coverage", group_cols=("n_rovers",))
        ax.errorbar(
            s["n_rovers"], s["mean"],
            yerr=[s["mean"] - s["ci95_low"], s["ci95_high"] - s["mean"]],
            marker="s", markersize=4, capsize=3, linewidth=1.5,
            label=ALGO_LABELS[algo], color=ALGO_COLORS[algo],
        )
    ax.set_xlabel("Swarm size $N$ (rovers)")
    ax.set_ylabel("Final coverage")
    ax.legend(frameon=False, fontsize=7)
    fig.savefig(path)
    plt.close(fig)


def figure_terrain_example(path: Path):
    """Illustrative terrain panel - regenerated from a fixed seed so the
    figure in the paper always matches the code."""
    _style()
    from lunar_swarm.terrain import generate_terrain

    terrain = generate_terrain(size=48, seed=1, n_craters=6, max_slope_deg=25.0)
    fig, axes = plt.subplots(1, 3, figsize=(6.6, 2.3))
    im0 = axes[0].imshow(terrain.elevation, cmap="gray")
    axes[0].set_title("Elevation $h$", fontsize=8)
    fig.colorbar(im0, ax=axes[0], fraction=0.046, label="m")

    im1 = axes[1].imshow(terrain.slope, cmap="magma")
    axes[1].set_title(r"Slope $\theta$", fontsize=8)
    fig.colorbar(im1, ax=axes[1], fraction=0.046, label="deg")

    composite = np.zeros(terrain.shape)
    composite[terrain.hazard_mask] = 1.0
    composite[terrain.shadow_mask] = 2.0
    axes[2].imshow(composite, cmap=matplotlib.colors.ListedColormap(
        ["#EEEEEE", "#C44E52", "#4C72B0"]), vmin=0, vmax=2)
    axes[2].set_title("Traversable / hazard / PSR", fontsize=8)

    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    fig.savefig(path)
    plt.close(fig)


# --------------------------------------------------------------------------
# provenance + macros
# --------------------------------------------------------------------------
def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def _package_versions() -> dict:
    import importlib.metadata as md
    out = {}
    for pkg in ["numpy", "scipy", "pandas", "stable-baselines3", "torch",
                "gymnasium", "statsmodels", "matplotlib", "streamlit"]:
        try:
            out[pkg] = md.version(pkg)
        except Exception:
            out[pkg] = "n/a"
    return out


def write_macros(main: pd.DataFrame, raw: pd.DataFrame, pc: pd.DataFrame,
                 anova: dict, two_way: pd.DataFrame, path: Path):
    """LaTeX macros for every number quoted in the prose."""
    def macro(name, value):
        return r"\newcommand{\%s}{%s}" % (name, value)

    cov = summarize(main, "final_coverage", ("algorithm",)).set_index("algorithm")
    cpe = summarize(main, "coverage_per_energy", ("algorithm",)).set_index("algorithm")

    lines = ["% AUTO-GENERATED by scripts/make_paper_assets.py -- do not edit by hand"]
    lines.append(macro("GenDate", date.today().isoformat()))
    lines.append(macro("GenCommit", _git_commit()))
    lines.append(macro("NTrialsMain", f"{len(raw):,}".replace(",", r"{,}")))
    lines.append(macro("NBlocks", str(anova["n_blocks"])))
    lines.append(macro("NSeeds", str(main["seed"].nunique())))
    lines.append(macro("NCommRadii", str(main["comm_radius"].nunique())))
    lines.append(macro("NFailureRates", str(main["failure_rate"].nunique())))
    lines.append(macro("CommRadiiList", ", ".join(str(int(v)) for v in sorted(main["comm_radius"].unique()))))
    lines.append(macro("FailureRatesList", ", ".join(f"{v:.0%}".replace("%", r"\%") for v in sorted(main["failure_rate"].unique()))))

    for algo in ALGO_ORDER:
        if algo not in cov.index:
            continue
        key = algo.replace("_", "")
        lines.append(macro(f"cov{key}", f"{cov.loc[algo, 'mean']:.3f}"))
        lines.append(macro(f"covsd{key}", f"{cov.loc[algo, 'sd']:.3f}"))
        lines.append(macro(f"cpe{key}", f"{cpe.loc[algo, 'mean']:.5f}"))

    lines.append(macro("AnovaF", f"{anova['f_stat']:.2f}"))
    lines.append(macro("AnovaDfT", str(anova["df_treatment"])))
    lines.append(macro("AnovaDfE", str(anova["df_error"])))
    lines.append(macro("AnovaP", _p_plain(anova["p_value"])))
    lines.append(macro("AnovaEta", f"{anova['partial_eta_squared']:.3f}"))

    inter_rows = [i for i in two_way.index if "interaction" in i]
    if inter_rows:
        r = two_way.loc[inter_rows[0]]
        lines.append(macro("InterF", f"{r['F']:.2f}"))
        lines.append(macro("InterP", _p_plain(r["PR(>F)"])))
        lines.append(macro("InterEta", f"{r['partial_eta_sq']:.3f}"))
        lines.append(macro("InterDf", str(int(r["df"]))))

    # best vs each baseline, for the abstract
    for _, r in pc.iterrows():
        a, b = r["algorithm_a"], r["algorithm_b"]
        tag = f"{a.replace('_','')}VS{b.replace('_','')}"
        lines.append(macro(f"diff{tag}", f"{r['mean_diff']:+.3f}"))
        lines.append(macro(f"p{tag}", _p_plain(r["p_holm"])))
        lines.append(macro(f"dz{tag}", f"{r['cohens_dz']:+.2f}"))

    versions = _package_versions()
    lines.append(macro("VerPython", platform.python_version()))
    lines.append(macro("VerSB", versions.get("stable-baselines3", "n/a")))
    lines.append(macro("VerTorch", versions.get("torch", "n/a")))
    lines.append(macro("VerNumpy", versions.get("numpy", "n/a")))
    lines.append(macro("VerScipy", versions.get("scipy", "n/a")))
    lines.append(macro("VerStatsmodels", versions.get("statsmodels", "n/a")))
    lines.append(macro("HostCPU", platform.processor() or platform.machine()))

    # These macros are always defined so the document compiles; a missing
    # value renders as a loud [MISSING] in the PDF rather than silently
    # vanishing or being mistaken for a real number.
    missing_marker = r"\textbf{[MISSING]}"
    cfg_path = PROJECT_ROOT / "models" / "ppo_seed0_training_config.json"
    rl_macros = {
        "RLTimesteps": missing_marker, "RLEnvs": missing_marker,
        "RLGamma": missing_marker, "RLLR": missing_marker,
        "RLArch": missing_marker,
    }
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text())
        arch = r"$\times$".join(str(n) for n in cfg.get("net_arch", []))
        rl_macros = {
            "RLTimesteps": f"{cfg['total_timesteps']:,}".replace(",", r"{,}"),
            "RLEnvs": str(cfg["n_envs"]),
            "RLGamma": str(cfg["gamma"]),
            "RLLR": str(cfg["learning_rate"]),
            "RLArch": f"${arch}$" if arch else missing_marker,
        }
    for name, value in rl_macros.items():
        lines.append(macro(name, value))
    lines.append(macro("NRLSeeds", str(raw[raw["algorithm"].str.startswith("rl:")]["algorithm"].nunique())))

    path.write_text("\n".join(lines) + "\n")

    missing = [n for n, v in rl_macros.items() if v == missing_marker]
    if missing:
        print(f"WARNING: no RL training config found; these macros are [MISSING]: {missing}")


def main() -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    if not MAIN_CSV.exists():
        raise SystemExit(f"missing {MAIN_CSV}; run scripts/run_paper_experiments.py first")

    raw = pd.read_csv(MAIN_CSV)
    main_df = collapse_rl_seeds(raw)

    # tables
    table_descriptive(
        main_df, "final_coverage", TABLES_DIR / "descriptive_coverage.tex",
        "Final coverage by algorithm, pooled over all conditions.",
        "tab:descriptive-coverage")
    table_descriptive(
        main_df, "coverage_per_energy", TABLES_DIR / "descriptive_cpe.tex",
        "Coverage per unit energy by algorithm, pooled over all conditions.",
        "tab:descriptive-cpe")
    pc = table_paired(
        main_df, "final_coverage", TABLES_DIR / "paired_coverage.tex",
        "Pairwise paired comparisons on final coverage, with Holm--Bonferroni "
        "corrected $p$-values and paired effect sizes.",
        "tab:paired-coverage")
    table_paired(
        main_df, "coverage_per_energy", TABLES_DIR / "paired_cpe.tex",
        "Pairwise paired comparisons on coverage per unit energy.",
        "tab:paired-cpe")
    two_way = table_two_way(
        main_df, "final_coverage", TABLES_DIR / "two_way_anova.tex",
        "Factorial ANOVA of final coverage. The interaction row tests whether the "
        "ranking of algorithms depends on communication radius.",
        "tab:two-way")
    table_by_condition(
        main_df, "final_coverage", "comm_radius", TABLES_DIR / "by_comm_radius.tex",
        "Final coverage by communication radius.", "tab:by-comm")
    table_by_condition(
        main_df, "rovers_alive", "failure_rate", TABLES_DIR / "by_failure_rate.tex",
        "Rovers surviving to end of mission by injected failure rate.", "tab:by-failure")
    table_rl_seed_spread(
        raw, TABLES_DIR / "rl_seed_spread.tex",
        "Variation across the three independently trained RL policies.",
        "tab:rl-seeds")

    anova = repeated_measures_anova(main_df, "final_coverage")

    # figures
    figure_metric_vs_comm(main_df, "final_coverage",
                          FIGURES_DIR / "coverage_vs_comm.pdf", "Final coverage")
    figure_metric_vs_comm(main_df, "coverage_per_energy",
                          FIGURES_DIR / "cpe_vs_comm.pdf", "Coverage per unit energy")
    figure_metric_vs_failure(main_df, "final_coverage",
                             FIGURES_DIR / "coverage_vs_failure.pdf", "Final coverage")
    figure_terrain_example(FIGURES_DIR / "terrain_example.pdf")
    if SWARM_CSV.exists():
        swarm = collapse_rl_seeds(pd.read_csv(SWARM_CSV))
        figure_swarm_size(swarm, FIGURES_DIR / "coverage_vs_swarm_size.pdf")
        table_by_condition(
            swarm, "final_coverage", "n_rovers", TABLES_DIR / "by_swarm_size.tex",
            "Final coverage by swarm size at fixed communication radius.",
            "tab:by-swarm")

    write_macros(main_df, raw, pc, anova, two_way, TABLES_DIR / "generated_macros.tex")

    print(f"wrote tables to {TABLES_DIR}")
    print(f"wrote figures to {FIGURES_DIR}")
    print(f"ANOVA: F({anova['df_treatment']},{anova['df_error']})={anova['f_stat']:.3f}, "
          f"p={anova['p_value']:.4g}")


if __name__ == "__main__":
    main()

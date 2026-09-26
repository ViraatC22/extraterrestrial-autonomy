"""Sample size for Study 2's primary test. VALIDATION seeds only.

The primary test (docs/V2_HYPOTHESES_DRAFT.md) is McNemar's exact test,
two-sided, alpha = 0.05, on mission success in the Mars condition, paired by
seed. Its power depends on two things:

  delta = p10 - p01   the true difference in success probability
                      (p10: only adaptive succeeds; p01: only fixed succeeds)
  psi   = p10 + p01   the discordance rate - how often the planners disagree

delta is the effect to detect, fixed in advance as a minimum effect of
interest (MIN_EFFECT below, with a sensitivity range). psi is a nuisance
parameter estimated here from validation missions run with the candidate v2
method. The estimated delta is recorded but deliberately NOT used to choose n:
sizing a study on its own pilot effect is how optimistic studies get planned.

Power is computed exactly (sum over the binomial distribution of discordant
counts, with the analysis code's own rejection rule) and checked by
simulation.

    python scripts/power_analysis.py run       # validation missions
    python scripts/power_analysis.py analyze   # grid, figure, recommendation
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from exonaut.experiments.v2_protocol import check_development_seeds

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "validation" / "power_analysis"
FIGURES = ROOT / "paper" / "figures"
META = json.loads((ROOT / "data/results/exonaut_main.metadata.json").read_text())

VALIDATION_SEEDS = list(range(200_000, 200_200))
SEED_USE = {"validation": VALIDATION_SEEDS}
PLANNERS = ("risk_aware_astar", "adaptive_risk_aware_astar")
ALPHA = 0.05
TARGET_POWER = 0.90
#: minimum effect of interest: 10 percentage points of mission success
MIN_EFFECT = 0.10
SENSITIVITY_EFFECTS = (0.05, 0.075, 0.10, 0.125, 0.15)
N_GRID = np.arange(50, 1001, 10)


#: No calibration method was accepted (CALIBRATION_AUDIT.md), and the
#: discordance rate depends on the method, so sizing is done for both leading
#: candidates. The project owner's choice decides which one applies.
METHODS = ("M3", "M2a")


def method_config(name: str) -> dict:
    """A calibration candidate's settings, exactly as the calibration study defined them."""
    fit = json.loads((ROOT / "data/validation/calibration/fit.json").read_text())
    return {
        "M3": {"class_assignment": "responsibility"},
        "M2a": {"epistemic_scale": fit["M2_scale_fit_on_moon"]},
    }[name]


def _job(args):
    body, seed, planner, method = args
    from exonaut.simulation import MissionConfig, run_mission

    config = MissionConfig(
        **{
            **META["base_config"],
            "body": body,
            "planner": planner,
            "prior_body": "moon",
            "engine": "v2",
            **method_config(method),
        }
    )
    r = run_mission(config, seed=seed)
    return {
        "method": method,
        "body": body,
        "seed": seed,
        "planner": planner,
        "success": bool(r.success),
        "termination": r.termination,
        "science_fraction": r.science_return / max(r.science_possible, 1e-9),
    }


def run() -> None:
    check_development_seeds(VALIDATION_SEEDS, "validation")
    jobs = [
        (b, s, p, m)
        for m in METHODS
        for b in ("mars", "moon")
        for s in VALIDATION_SEEDS
        for p in PLANNERS
    ]
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(_job, jobs, chunksize=2))
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / "validation_missions.csv", index=False)
    print(f"{len(rows)} validation missions written")


# ---------------------------------------------------------------------------
# exact power of the analysis code's McNemar test
# ---------------------------------------------------------------------------


def critical_counts(max_d: int, alpha: float = ALPHA) -> np.ndarray:
    """k[D]: reject when min(W, D - W) <= k[D]; -1 if no W rejects.

    Two-sided exact binomial test at p = 0.5, as scipy.stats.binomtest (used by
    experiments.analysis.paired_binary) computes it; the distribution is
    symmetric, so its p-value is min(1, 2 * P(X <= min(W, D - W))).
    tests/test_power_analysis.py checks this against binomtest directly.
    """
    k = np.full(max_d + 1, -1)
    for d in range(1, max_d + 1):
        tail = stats.binom.cdf(np.arange(d // 2 + 1), d, 0.5)
        ok = np.nonzero(np.minimum(1.0, 2 * tail) <= alpha)[0]
        k[d] = ok.max() if ok.size else -1
    return k


def exact_power(n: int, delta: float, psi: float, k: np.ndarray) -> float:
    if delta > psi or psi <= 0:
        return float("nan")
    pi = (psi + delta) / (2 * psi)  # P(a discordant pair favours adaptive)
    d = np.arange(n + 1)
    p_d = stats.binom.pmf(d, n, psi)
    kd = k[: n + 1]
    lower = np.where(kd >= 0, stats.binom.cdf(kd, d, pi), 0.0)
    upper = np.where(kd >= 0, stats.binom.sf(d - kd - 1, d, pi), 0.0)
    return float(np.sum(p_d * (lower + upper)))


def simulated_power(n: int, delta: float, psi: float, sims: int = 20_000, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    p10, p01 = (psi + delta) / 2, (psi - delta) / 2
    counts = rng.multinomial(n, [p10, p01, 1 - psi], size=sims)
    rejections = 0
    for w, loss, _ in counts:
        d = w + loss
        if d and stats.binomtest(int(w), int(d), 0.5).pvalue <= ALPHA:
            rejections += 1
    return rejections / sims


def wilson(k: int, n: int, level: float) -> tuple[float, float]:
    ci = stats.binomtest(k, n).proportion_ci(confidence_level=level, method="wilson")
    return float(ci.low), float(ci.high)


def analyze_method(missions: pd.DataFrame, k: np.ndarray) -> dict:
    wide = missions.pivot_table(
        index=["body", "seed"], columns="planner", values="success"
    ).reset_index()
    out = {"alpha": ALPHA, "target_power": TARGET_POWER, "min_effect": MIN_EFFECT}
    for body in ("mars", "moon"):
        g = wide[wide.body == body]
        a = g["adaptive_risk_aware_astar"].astype(bool)
        f = g["risk_aware_astar"].astype(bool)
        n10, n01, n = int((a & ~f).sum()), int((~a & f).sum()), len(g)
        low, high = wilson(n10 + n01, n, 0.80)
        out[body] = {
            "n_seeds": n,
            "success_adaptive": float(a.mean()),
            "success_fixed": float(f.mean()),
            "only_adaptive": n10,
            "only_fixed": n01,
            "psi_hat": (n10 + n01) / n,
            "psi_upper80": high,  # one-sided 90% upper bound
            "psi_lower80": low,
            "delta_hat_not_used_for_sizing": (n10 - n01) / n,
        }
    mars = out["mars"]
    psis = sorted({mars["psi_hat"], mars["psi_upper80"], 0.20, 0.30, 0.40, 0.50})
    grid = pd.DataFrame(
        [
            {"n": int(n), "delta": d, "psi": p, "power": exact_power(int(n), d, p, k)}
            for n in N_GRID
            for d in SENSITIVITY_EFFECTS
            for p in psis
        ]
    )

    def n_for(delta, psi, power):
        ok = grid[(grid.delta == delta) & (np.isclose(grid.psi, psi)) & (grid.power >= power)]
        return int(ok.n.min()) if len(ok) else None

    out["sample_size_table"] = [
        {"delta": d, "psi": p, "n_power80": n_for(d, p, 0.80), "n_power90": n_for(d, p, 0.90)}
        for d in SENSITIVITY_EFFECTS
        for p in psis
    ]
    recommended = n_for(MIN_EFFECT, mars["psi_upper80"], TARGET_POWER)
    out["recommended_n"] = recommended
    out["recommendation_rule"] = (
        f"smallest n in steps of 10 with exact power >= {TARGET_POWER} for delta = {MIN_EFFECT} "
        "at the one-sided 90% upper Wilson bound of the Mars discordance rate"
    )
    if recommended:
        out["power_at_recommended"] = {
            "exact": exact_power(recommended, MIN_EFFECT, mars["psi_upper80"], k),
            "simulated": simulated_power(recommended, MIN_EFFECT, mars["psi_upper80"]),
            "exact_at_psi_hat": exact_power(recommended, MIN_EFFECT, mars["psi_hat"], k),
        }
        sci = missions.pivot_table(
            index=["body", "seed"], columns="planner", values="science_fraction"
        )
        diff = (sci["adaptive_risk_aware_astar"] - sci["risk_aware_astar"]).loc["mars"]
        sd = float(diff.std(ddof=1))
        z = stats.norm.ppf(1 - ALPHA / 2) + stats.norm.ppf(0.80)
        out["mars_science"] = {
            "sd_paired_difference": sd,
            "detectable_difference_80pct_power_at_n": float(z * sd / np.sqrt(recommended)),
        }
    return out, grid


def analyze() -> dict:
    all_missions = pd.read_csv(OUT / "validation_missions.csv")
    k = critical_counts(int(N_GRID.max()))
    summary, grids = {"pool_size_available": 1000}, []
    for method in METHODS:
        out, grid = analyze_method(all_missions[all_missions.method == method], k)
        summary[method] = out
        grids.append(grid.assign(method=method))
    pd.concat(grids).to_csv(OUT / "power_grid.csv", index=False)
    pd.DataFrame(
        [{"method": m, **row} for m in METHODS for row in summary[m]["sample_size_table"]]
    ).to_csv(OUT / "sample_size_table.csv", index=False)
    (OUT / "power_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    figure(pd.concat(grids), summary)
    macros(summary)
    markdown(summary)
    print(
        json.dumps(
            {
                m: {k: summary[m][k] for k in ("recommended_n",)} | {"mars": summary[m]["mars"]}
                for m in METHODS
            },
            indent=2,
        )
    )
    return summary


METHOD_WORDS = {"M3": "MThree", "M2a": "MTwoA"}


def markdown(summary: dict) -> None:
    """Generated results for docs/POWER_ANALYSIS.md (no typed numbers)."""
    out = [
        "<!-- AUTO-GENERATED by scripts/power_analysis.py. Do not edit. -->",
        "# Power analysis: validation results (generated)",
        "",
        f"Primary test: McNemar exact, two-sided, alpha = {ALPHA}. Target power {TARGET_POWER}. "
        f"Minimum effect of interest {MIN_EFFECT} (difference in success probability). "
        f"Seed pool available per condition: {summary['pool_size_available']}.",
        "",
        "## Validation estimates (Mars, lunar prior)",
        "",
        "| method | seeds | success adaptive | success fixed | only adaptive | only fixed | "
        "discordance psi (point) | psi upper bound (one-sided 90%) | observed difference (not used for sizing) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for method in METHODS:
        m = summary[method]["mars"]
        out.append(
            f"| {method} | {m['n_seeds']} | {m['success_adaptive']:.3f} | {m['success_fixed']:.3f} | "
            f"{m['only_adaptive']} | {m['only_fixed']} | {m['psi_hat']:.3f} | {m['psi_upper80']:.3f} | "
            f"{m['delta_hat_not_used_for_sizing']:+.3f} |"
        )
    out += ["", "## Recommended n (Mars condition, matched seeds)", ""]
    for method in METHODS:
        r = summary[method]
        line = f"- **{method}: n = {r['recommended_n']}** ({r['recommendation_rule']})"
        if r.get("power_at_recommended"):
            pw = r["power_at_recommended"]
            line += (
                f". Power at that n: exact {pw['exact']:.3f}, simulated {pw['simulated']:.3f}; "
                f"at the point estimate of psi, {pw['exact_at_psi_hat']:.3f}. Secondary (science "
                f"fraction): smallest difference detectable with 80% power at that n = "
                f"{r['mars_science']['detectable_difference_80pct_power_at_n']:.3f} "
                f"(sd of paired differences {r['mars_science']['sd_paired_difference']:.3f})."
            )
        out.append(line)
    out += [
        "",
        "## Sensitivity: n for 80% and 90% power",
        "",
        "| method | effect | psi | n (80%) | n (90%) |",
        "|---|---|---|---|---|",
    ]
    for method in METHODS:
        for row in summary[method]["sample_size_table"]:
            out.append(
                f"| {method} | {row['delta']:.3f} | {row['psi']:.3f} | {row['n_power80']} | {row['n_power90']} |"
            )
    (OUT / "RESULTS.md").write_text("\n".join(out) + "\n")


def macros(summary: dict) -> None:
    """Every number the paper quotes about sample size, from power_summary.json."""
    m = [
        "% AUTO-GENERATED by scripts/power_analysis.py from validation missions. Not confirmatory.",
        rf"\newcommand{{\PowAlpha}}{{{ALPHA}}}",
        rf"\newcommand{{\PowTarget}}{{{TARGET_POWER:.2f}}}",
        rf"\newcommand{{\PowMinEffect}}{{{MIN_EFFECT:.2f}}}",
        rf"\newcommand{{\PowPool}}{{{summary['pool_size_available']}}}",
    ]
    for method, word in METHOD_WORDS.items():
        out = summary[method]
        mars, moon = out["mars"], out["moon"]
        p = f"Pow{word}"
        m += [
            rf"\newcommand{{\{p}ValSeeds}}{{{mars['n_seeds']}}}",
            rf"\newcommand{{\{p}MarsSuccessAdaptive}}{{{mars['success_adaptive']:.3f}}}",
            rf"\newcommand{{\{p}MarsSuccessFixed}}{{{mars['success_fixed']:.3f}}}",
            rf"\newcommand{{\{p}MarsOnlyAdaptive}}{{{mars['only_adaptive']}}}",
            rf"\newcommand{{\{p}MarsOnlyFixed}}{{{mars['only_fixed']}}}",
            rf"\newcommand{{\{p}MarsPsiHat}}{{{mars['psi_hat']:.3f}}}",
            rf"\newcommand{{\{p}MarsPsiUpper}}{{{mars['psi_upper80']:.3f}}}",
            rf"\newcommand{{\{p}MarsDeltaHat}}{{{mars['delta_hat_not_used_for_sizing']:+.3f}}}",
            rf"\newcommand{{\{p}MoonSuccessAdaptive}}{{{moon['success_adaptive']:.3f}}}",
            rf"\newcommand{{\{p}MoonSuccessFixed}}{{{moon['success_fixed']:.3f}}}",
            rf"\newcommand{{\{p}RecommendedN}}{{{out['recommended_n']}}}",
        ]
        if out.get("power_at_recommended"):
            pw = out["power_at_recommended"]
            m.append(rf"\newcommand{{\{p}AtNExact}}{{{pw['exact']:.3f}}}")
            m.append(rf"\newcommand{{\{p}AtNSimulated}}{{{pw['simulated']:.3f}}}")
            m.append(rf"\newcommand{{\{p}AtNPsiHat}}{{{pw['exact_at_psi_hat']:.3f}}}")
            sci = out["mars_science"]
            m.append(rf"\newcommand{{\{p}SciSd}}{{{sci['sd_paired_difference']:.3f}}}")
            m.append(
                rf"\newcommand{{\{p}SciDetectable}}{{{sci['detectable_difference_80pct_power_at_n']:.3f}}}"
            )
    (ROOT / "paper" / "tables" / "exonaut_power_macros.tex").write_text("\n".join(m) + "\n")


def figure(grid: pd.DataFrame, summary: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(METHODS), figsize=(10, 3.8), sharey=True)
    for ax, method in zip(axes, METHODS, strict=True):
        psi = summary[method]["mars"]["psi_upper80"]
        g = grid[(grid.method == method) & np.isclose(grid.psi, psi)]
        for d in SENSITIVITY_EFFECTS:
            line = g[g.delta == d]
            main = d == MIN_EFFECT
            ax.plot(
                line.n, line.power, "-" if main else "--", lw=2 if main else 1, label=f"Δ = {d:.3f}"
            )
        ax.axhline(TARGET_POWER, color="grey", lw=0.8)
        if summary[method]["recommended_n"]:
            ax.axvline(summary[method]["recommended_n"], color="grey", lw=0.8, ls=":")
        ax.set_title(f"{method}: discordance ψ = {psi:.3f} (upper 90% bound)", fontsize=9)
        ax.set_xlabel("matched seeds (pairs), Mars condition")
        ax.set_ylim(0, 1)
    axes[0].set_ylabel("power, McNemar exact, α = 0.05")
    axes[-1].legend(fontsize=8, frameon=False)
    fig.tight_layout()
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / "v2_power_curve.pdf", metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(OUT / "v2_power_curve.png", dpi=150, metadata={"Software": None})
    plt.close(fig)


if __name__ == "__main__":
    {"run": run, "analyze": analyze}[sys.argv[1] if len(sys.argv) > 1 else "analyze"]()

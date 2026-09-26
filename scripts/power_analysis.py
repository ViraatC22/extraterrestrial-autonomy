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


def selected_scale() -> float:
    path = ROOT / "data/validation/calibration/selection.json"
    return float(json.loads(path.read_text())["epistemic_scale"])


def _job(args):
    body, seed, planner, scale = args
    from exonaut.simulation import MissionConfig, run_mission

    config = MissionConfig(
        **{
            **META["base_config"],
            "body": body,
            "planner": planner,
            "prior_body": "moon",
            "engine": "v2",
            "epistemic_scale": scale,
        }
    )
    r = run_mission(config, seed=seed)
    return {
        "body": body,
        "seed": seed,
        "planner": planner,
        "epistemic_scale": scale,
        "success": bool(r.success),
        "termination": r.termination,
        "science_fraction": r.science_return / max(r.science_possible, 1e-9),
    }


def run() -> None:
    check_development_seeds(VALIDATION_SEEDS, "validation")
    scale = selected_scale()
    jobs = [(b, s, p, scale) for b in ("mars", "moon") for s in VALIDATION_SEEDS for p in PLANNERS]
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


def analyze() -> dict:
    missions = pd.read_csv(OUT / "validation_missions.csv")
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
    k = critical_counts(int(N_GRID.max()))
    psis = sorted({mars["psi_hat"], mars["psi_upper80"], 0.20, 0.30, 0.40, 0.50})
    rows = [
        {"n": int(n), "delta": d, "psi": p, "power": exact_power(int(n), d, p, k)}
        for n in N_GRID
        for d in SENSITIVITY_EFFECTS
        for p in psis
    ]
    grid = pd.DataFrame(rows)
    grid.to_csv(OUT / "power_grid.csv", index=False)

    def n_for(delta, psi, power):
        ok = grid[(grid.delta == delta) & (np.isclose(grid.psi, psi)) & (grid.power >= power)]
        return int(ok.n.min()) if len(ok) else None

    table = []
    for d in SENSITIVITY_EFFECTS:
        for p in psis:
            table.append(
                {
                    "delta": d,
                    "psi": p,
                    "n_power80": n_for(d, p, 0.80),
                    "n_power90": n_for(d, p, 0.90),
                }
            )
    pd.DataFrame(table).to_csv(OUT / "sample_size_table.csv", index=False)
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
        out["pool_size_available"] = 1000
    # the secondary science outcome: smallest difference detectable at n
    sci = missions.pivot_table(index=["body", "seed"], columns="planner", values="science_fraction")
    diff = (sci["adaptive_risk_aware_astar"] - sci["risk_aware_astar"]).loc["mars"]
    sd = float(diff.std(ddof=1))
    if recommended:
        z = stats.norm.ppf(1 - ALPHA / 2) + stats.norm.ppf(0.80)
        out["mars_science"] = {
            "sd_paired_difference": sd,
            "detectable_difference_80pct_power_at_n": float(z * sd / np.sqrt(recommended)),
        }
    (OUT / "power_summary.json").write_text(json.dumps(out, indent=2) + "\n")
    figure(grid, mars, recommended)
    print(json.dumps(out, indent=2))
    return out


def figure(grid: pd.DataFrame, mars: dict, recommended: int | None) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    psi = mars["psi_upper80"]
    for d in SENSITIVITY_EFFECTS:
        g = grid[(grid.delta == d) & np.isclose(grid.psi, psi)]
        style = "-" if d == MIN_EFFECT else "--"
        ax.plot(g.n, g.power, style, lw=2 if d == MIN_EFFECT else 1, label=f"Δ = {d:.3f}")
    ax.axhline(TARGET_POWER, color="grey", lw=0.8)
    if recommended:
        ax.axvline(recommended, color="grey", lw=0.8, ls=":")
    ax.set_xlabel("matched seeds (pairs) in the Mars condition")
    ax.set_ylabel("power, McNemar exact, α = 0.05")
    ax.set_ylim(0, 1)
    ax.set_title(f"discordance ψ = {psi:.3f} (upper 90% bound from validation)", fontsize=9)
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / "v2_power_curve.pdf")
    fig.savefig(OUT / "v2_power_curve.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    {"run": run, "analyze": analyze}[sys.argv[1] if len(sys.argv) > 1 else "analyze"]()

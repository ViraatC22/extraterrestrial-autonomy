"""Uncertainty-calibration study for the v2 learner. TRAIN + VALIDATION only.

Protocol (docs/CALIBRATION_AUDIT.md, written and committed before `evaluate`):

  diagnose   TRAIN seeds. Runs the v2 adaptive planner and diagnostic
             ablations that each remove one suspected cause of
             miscalibration using simulator truth. Ablations are for
             attribution only; none is a candidate method.
  fit        TRAIN rows only. Fits each candidate's single parameter.
  evaluate   VALIDATION seeds. Runs every candidate once and applies the
             pre-stated acceptance criteria.

Every mission row, belief record and prediction is written as a raw artifact
under data/validation/calibration/, and every summary is computed from those
files, so the numbers in the audit and the paper can be regenerated.

    python scripts/calibration_study.py diagnose
    python scripts/calibration_study.py fit
    python scripts/calibration_study.py evaluate
    python scripts/calibration_study.py report     # summaries + figures only
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from exonaut.experiments.v2_protocol import check_development_seeds

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "validation" / "calibration"
FIGURES = ROOT / "paper" / "figures"
META = json.loads((ROOT / "data/results/exonaut_main.metadata.json").read_text())

#: Train seeds 100000-100059 calibrated the priors; missions on those
#: terrains would flatter the lunar prior, so diagnosis and fitting use the
#: next 100 train seeds. Evaluation uses the first 100 validation seeds.
TRAIN_SEEDS = list(range(100_100, 100_200))
VALIDATION_SEEDS = list(range(200_000, 200_100))
BODIES = ("mars", "moon")
LEVELS = (0.50, 0.80, 0.90, 0.95)
#: every seed this script touches, by split (checked by tests)
SEED_USE = {"train": TRAIN_SEEDS, "validation": VALIDATION_SEEDS}


def base_config(body: str, **extra) -> dict:
    return {
        **META["base_config"],
        "body": body,
        "planner": "adaptive_risk_aware_astar",
        "prior_body": "moon",
        "engine": "v2",
        **extra,
    }


# ---------------------------------------------------------------------------
# one mission, instrumented
# ---------------------------------------------------------------------------


def _job(args):
    """Run one mission; return belief records and per-step predictions.

    `variant` names either a candidate (config parameters only) or a
    diagnostic ablation (which patches the learner with simulator truth, in
    this worker process only - workers are recycled after every task).
    """
    body, seed, variant, params, split = args
    from exonaut.autonomy import world_model as W
    from exonaut.autonomy.priors import default_prior
    from exonaut.environments import TRUE_CLASS_PARAMS, make_environment
    from exonaut.simulation import MissionConfig, run_mission

    truth = TRUE_CLASS_PARAMS[body]
    prior = default_prior("moon")
    if variant == "ablate_class":
        # diagnostic: fold readings into the TRUE class (no misclassification)
        original = W.AdaptiveWorldModel.ingest_slip

        def ingest(self, record):
            saved = self.terrain_class[record.row, record.col]
            self.terrain_class[record.row, record.col] = record.terrain_class
            try:
                original(self, record)
            finally:
                self.terrain_class[record.row, record.col] = saved

        W.AdaptiveWorldModel.ingest_slip = ingest
    elif variant == "ablate_dispersion":
        # diagnostic: the prior's aleatoric spread replaced by the true one
        prior = {**prior, "aleatoric_sd": {int(k): v.slip_dispersion for k, v in truth.items()}}
    elif variant == "ablate_prior_mean":
        # diagnostic: prior centred on the true class means (no prior conflict)
        prior = {
            **prior,
            "means": {int(k): (v.slip_mean, prior["means"][int(k)][1]) for k, v in truth.items()},
        }

    config = MissionConfig(**base_config(body, **params))
    r = run_mission(config, seed=seed, prior=prior, collect_history=True)
    terrain = make_environment(body, seed=seed, size=config.size)

    beliefs = []
    for d in r.decisions:
        for k, b in d["class_belief"].items():
            if b["n_observations"] < 1:
                continue
            beliefs.append(
                {
                    "split": split,
                    "body": body,
                    "variant": variant,
                    "seed": seed,
                    "step": d["step"],
                    "cls": int(k),
                    "n": b["n_observations"],
                    "mean": b["mean"],
                    "sd": b["epistemic_sd"],
                    "truth": truth[int(k)].slip_mean,
                }
            )
    predictions = []
    for f in r.history:
        p = f.get("prediction")
        if not p or f["reason"] in ("hazard_refused", "off_map", "insufficient_energy"):
            continue
        tr, tc = p["target"]
        predictions.append(
            {
                "split": split,
                "body": body,
                "variant": variant,
                "seed": seed,
                "step": f["step"],
                "pred_mean": p["mean"],
                "pred_sd": p["sd"],
                "p_severe": p["p_severe"],
                "observed": p["observed"],
                "believed_cls": p["believed_class"],
                "true_cls": int(terrain.terrain_class[tr, tc]),
                "slip": f["slip"],
                # the reading the learner folds in (slope removed, as it does)
                "adjusted": float(np.clip(f["slip"] - 0.01 * terrain.slope[tr, tc], 0, 1)),
            }
        )
    mission = {
        "split": split,
        "body": body,
        "variant": variant,
        "seed": seed,
        "termination": r.termination,
        "success": r.success,
        "science_fraction": r.science_return / max(r.science_possible, 1e-9),
    }
    return beliefs, predictions, mission


def run(jobs, tag: str, isolate: bool = False) -> None:
    """Run jobs in parallel. `isolate` gives each job a fresh process, which
    the diagnostic ablations need because they patch the learner in place."""
    OUT.mkdir(parents=True, exist_ok=True)
    pool = ProcessPoolExecutor(max_tasks_per_child=1) if isolate else ProcessPoolExecutor()
    with pool as ex:
        results = list(ex.map(_job, jobs, chunksize=1 if isolate else 2))
    beliefs = pd.DataFrame([row for b, _, _ in results for row in b])
    predictions = pd.DataFrame([row for _, p, _ in results for row in p])
    missions = pd.DataFrame([m for _, _, m in results])
    beliefs.to_csv(OUT / f"{tag}_beliefs{SUFFIX[tag]}", index=False)
    predictions.to_csv(OUT / f"{tag}_predictions{SUFFIX[tag]}", index=False)
    missions.to_csv(OUT / f"{tag}_missions.csv", index=False)
    print(
        f"{tag}: {len(missions)} missions, {len(beliefs)} belief rows, {len(predictions)} predictions"
    )


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


def _z(level: float) -> float:
    from scipy.stats import norm

    return float(norm.ppf(0.5 + level / 2))


def coverage_table(beliefs: pd.DataFrame, by: list[str], n_boot: int = 400) -> pd.DataFrame:
    """Class-mean interval coverage, with a 95% bootstrap CI clustered by mission."""
    rng = np.random.default_rng(0)
    rows = []
    for key, g in beliefs.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        z = (g["mean"] - g["truth"]).abs() / g["sd"]
        seeds = g["seed"].to_numpy()
        unique = np.unique(seeds)
        entry = dict(zip(by, key, strict=True))
        entry["records"] = len(g)
        entry["missions"] = len(unique)
        entry["median_sd"] = float(g["sd"].median())
        entry["median_abs_error"] = float((g["mean"] - g["truth"]).abs().median())
        for level in LEVELS:
            hit = (z <= _z(level)).to_numpy()
            entry[f"cov{int(level * 100)}"] = float(hit.mean())
            per = pd.Series(hit).groupby(seeds).agg(["sum", "count"])
            boots = []
            for _ in range(n_boot):
                pick = rng.choice(unique, size=len(unique))
                s = per.loc[pick]
                boots.append(s["sum"].sum() / s["count"].sum())
            entry[f"cov{int(level * 100)}_lo"] = float(np.quantile(boots, 0.025))
            entry[f"cov{int(level * 100)}_hi"] = float(np.quantile(boots, 0.975))
        rows.append(entry)
    return pd.DataFrame(rows)


def predictive_table(pred: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Per-step predictive calibration: interval coverage and severe-slip Brier."""
    rows = []
    for key, g in pred.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        entry = dict(zip(by, key, strict=True))
        z = (g["slip"] - g["pred_mean"]).abs() / g["pred_sd"]
        entry["steps"] = len(g)
        for level in LEVELS:
            entry[f"pcov{int(level * 100)}"] = float((z <= _z(level)).mean())
        severe = (g["slip"] >= 0.8).astype(float)
        entry["severe_rate"] = float(severe.mean())
        entry["mean_p_severe"] = float(g["p_severe"].mean())
        entry["brier_severe"] = float(((g["p_severe"] - severe) ** 2).mean())
        rows.append(entry)
    return pd.DataFrame(rows)


def reliability(pred: pd.DataFrame) -> pd.DataFrame:
    edges = [0, 0.01, 0.05, 0.1, 0.2, 0.5, 1.0000001]
    g = pred.assign(bin=pd.cut(pred["p_severe"], edges, right=False))
    out = g.groupby(["variant", "body", "bin"], observed=True).agg(
        predicted=("p_severe", "mean"),
        observed=("slip", lambda s: float((s >= 0.8).mean())),
        steps=("slip", "size"),
    )
    return out.reset_index()


# ---------------------------------------------------------------------------
# phases
# ---------------------------------------------------------------------------

DIAGNOSTICS = ("v2", "ablate_class", "ablate_dispersion", "ablate_prior_mean")
#: raw-file suffix per phase (later phases are compressed)
SUFFIX = {"diagnose": ".csv", "fit_m3": ".csv.gz", "evaluate": ".csv.gz"}
RESPONSIBILITY = {"class_assignment": "responsibility"}


def _read(tag: str, kind: str) -> pd.DataFrame:
    return pd.read_csv(OUT / f"{tag}_{kind}{SUFFIX[tag]}")


def diagnose() -> None:
    check_development_seeds(TRAIN_SEEDS, "train")
    jobs = [(b, s, v, {}, "train") for v in DIAGNOSTICS for b in BODIES for s in TRAIN_SEEDS]
    run(jobs, "diagnose", isolate=True)


def conformal_scale(beliefs: pd.DataFrame) -> float:
    """s = max(1, q / 1.96), q the ceil((n+1) 0.95)-th smallest |m - truth| / sd."""
    z = ((beliefs["mean"] - beliefs["truth"]).abs() / beliefs["sd"]).to_numpy()
    n = len(z)
    q = float(np.sort(z)[min(n - 1, int(np.ceil((n + 1) * 0.95)) - 1)])
    return max(1.0, q / _z(0.95))


def fit() -> dict:
    """Fit each candidate's one parameter on TRAIN rows (see CALIBRATION_AUDIT.md)."""
    check_development_seeds(TRAIN_SEEDS, "train")
    # M3 has no parameter, but M4 fits its scale on M3's own train residuals
    run([(b, s, "M3", RESPONSIBILITY, "train") for b in BODIES for s in TRAIN_SEEDS], "fit_m3")
    v2 = _read("diagnose", "beliefs").query("variant == 'v2'")
    m3 = _read("fit_m3", "beliefs")
    params = {}
    for body in BODIES:
        params[f"M2_scale_fit_on_{body}"] = conformal_scale(v2[v2.body == body])
        params[f"M4_scale_fit_on_{body}"] = conformal_scale(m3[m3.body == body])
    (OUT / "fit.json").write_text(json.dumps(params, indent=2) + "\n")
    print(json.dumps(params, indent=2))
    return params


def candidates(params: dict) -> dict:
    """The pre-specified candidates, in the selection preference order."""
    return {
        "M1": {},
        "M3": dict(RESPONSIBILITY),
        "M2a": {"epistemic_scale": params["M2_scale_fit_on_moon"]},
        "M4a": {**RESPONSIBILITY, "epistemic_scale": params["M4_scale_fit_on_moon"]},
        "M2b": {"epistemic_scale": params["M2_scale_fit_on_mars"]},
        "M4b": {**RESPONSIBILITY, "epistemic_scale": params["M4_scale_fit_on_mars"]},
    }


def evaluate() -> None:
    check_development_seeds(VALIDATION_SEEDS, "validation")
    params = json.loads((OUT / "fit.json").read_text())
    jobs = [
        (b, s, name, cfg, "validation")
        for name, cfg in candidates(params).items()
        for b in BODIES
        for s in VALIDATION_SEEDS
    ]
    run(jobs, "evaluate")


def accepted(cov: pd.DataFrame, name: str) -> dict:
    """The pre-specified acceptance rule (CALIBRATION_AUDIT.md section 3)."""
    mars = cov[(cov.variant == name) & (cov.body == "mars")].iloc[0]
    moon = cov[(cov.variant == name) & (cov.body == "moon")].iloc[0]
    checks = {
        "mars_95_in_[0.90,0.99]": bool(0.90 <= mars.cov95 <= 0.99),
        "mars_50_within_0.10": bool(abs(mars.cov50 - 0.50) <= 0.10),
        "mars_80_within_0.10": bool(abs(mars.cov80 - 0.80) <= 0.10),
        "mars_90_within_0.10": bool(abs(mars.cov90 - 0.90) <= 0.10),
        "moon_95_at_least_0.90": bool(moon.cov95 >= 0.90),
    }
    max_err = max(abs(mars[f"cov{int(level * 100)}"] - level) for level in LEVELS)
    return {
        "checks": checks,
        "accepted": all(checks.values()),
        "mars_max_coverage_error": float(max_err),
    }


def select() -> dict:
    """Apply the acceptance and selection rule to the validation coverage."""
    params = json.loads((OUT / "fit.json").read_text())
    cov = pd.read_csv(OUT / "evaluate_coverage.csv")
    order = list(candidates(params))
    verdicts = {name: accepted(cov, name) for name in order}
    chosen = next((n for n in order if verdicts[n]["accepted"]), None)
    best = min(order, key=lambda n: verdicts[n]["mars_max_coverage_error"])
    selection = {
        "status": "ACCEPTED" if chosen else "NOT ACCEPTED",
        "selected": chosen,
        "best_available_if_none_accepted": None if chosen else best,
        "config": candidates(params)[chosen or best],
        "epistemic_scale": candidates(params)[chosen or best].get("epistemic_scale", 1.0),
        "class_assignment": candidates(params)[chosen or best].get("class_assignment", "hard"),
        "verdicts": verdicts,
        "rule": "first accepted in order " + " > ".join(order),
    }
    (OUT / "selection.json").write_text(json.dumps(selection, indent=2) + "\n")
    print(json.dumps({k: selection[k] for k in ("status", "selected", "config")}, indent=2))
    return selection


def report() -> None:
    summaries = {}
    for tag in ("diagnose", "fit_m3", "evaluate"):
        path = OUT / f"{tag}_beliefs{SUFFIX[tag]}"
        if not path.exists():
            continue
        beliefs = _read(tag, "beliefs")
        pred = _read(tag, "predictions")
        cov = coverage_table(beliefs, ["variant", "body"])
        cov.to_csv(OUT / f"{tag}_coverage.csv", index=False)
        by_class = coverage_table(beliefs, ["variant", "body", "cls"], n_boot=100)
        by_class.to_csv(OUT / f"{tag}_coverage_by_class.csv", index=False)
        n_bins = pd.cut(
            beliefs["n"], [0, 2, 5, 10, 20, 10_000], labels=["1-2", "3-5", "6-10", "11-20", ">20"]
        )
        by_n = coverage_table(
            beliefs.assign(nbin=n_bins.astype(str)), ["variant", "body", "nbin"], n_boot=100
        )
        by_n.to_csv(OUT / f"{tag}_coverage_by_n.csv", index=False)
        ptab = predictive_table(pred, ["variant", "body"])
        ptab.to_csv(OUT / f"{tag}_predictive.csv", index=False)
        reliability(pred).to_csv(OUT / f"{tag}_reliability.csv", index=False)
        # the estimand the learner converges to: mean slope-adjusted reading per true class
        estimand = (
            pred[pred.variant == pred.variant.iloc[0]]
            .groupby(["body", "true_cls"])["adjusted"]
            .agg(["mean", "count"])
            .reset_index()
        )
        estimand.to_csv(OUT / f"{tag}_reading_means.csv", index=False)
        misclass = (
            pred[(pred.variant == pred.variant.iloc[0]) & pred.observed]
            .assign(wrong=lambda d: d.believed_cls != d.true_cls)
            .groupby("body")["wrong"]
            .mean()
        )
        summaries[tag] = {
            "coverage": cov.to_dict(orient="records"),
            "predictive": ptab.to_dict(orient="records"),
            "misclassified_reading_share": misclass.to_dict(),
        }
    (OUT / "summary.json").write_text(json.dumps(summaries, indent=2, default=float) + "\n")
    print(
        json.dumps(
            {
                k: [(r["variant"], r["body"], round(r["cov95"], 3)) for r in v["coverage"]]
                for k, v in summaries.items()
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"diagnose": diagnose, "fit": fit, "evaluate": evaluate, "report": report, "select": select}[
        phase
    ]()

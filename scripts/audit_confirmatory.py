r"""Post-hoc audits of the confirmatory result.

These are *not* confirmatory analyses and were not in the analysis plan. They
exist because checking the results turned up reasons to doubt what two of them
mean, and the paper has to say so with numbers rather than adjectives.

1. Fault exposure. Re-runs every mission in the "hardware faults" condition
   (they reproduce the committed rows exactly; the script verifies this) and
   counts which scheduled faults actually fired before the mission ended.

2. Learner calibration. On VALIDATION seeds only, checks how often the
   adaptive planner's 95% interval for each terrain class's mean slip contains
   the true value, under the committed update rule and under a corrected one.

Writes data/results/audit_*.csv and paper/tables/exonaut_audit_macros.tex.

    python scripts/audit_confirmatory.py
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from exonaut.autonomy import world_model as W
from exonaut.environments import TRUE_CLASS_PARAMS
from exonaut.simulation import MissionConfig, run_mission

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results"
MACROS = ROOT / "paper" / "tables" / "exonaut_audit_macros.tex"
META = json.loads((RESULTS / "exonaut_main.metadata.json").read_text())
CONDITIONS = {c["name"]: c for c in META["conditions"]}
VALIDATION_SEEDS = range(200000, 200040)


def _fault_job(args):
    planner, seed = args
    cond = CONDITIONS["mars_faults"]
    cfg = MissionConfig(
        **{
            **META["base_config"],
            "body": cond["body"],
            "planner": planner,
            "prior_body": cond["prior_body"],
            **cond["overrides"],
        }
    )
    r = run_mission(cfg, seed=int(seed), collect_history=True)
    fired = [f for frame in r.history for f in frame["faults"]]
    return planner, int(seed), len(fired), r.termination, r.science_return, r.energy_spent


def fault_exposure() -> tuple[pd.DataFrame, dict]:
    rows = pd.read_csv(RESULTS / "exonaut_main.csv")
    rows = rows[rows.condition == "mars_faults"]
    with ProcessPoolExecutor() as ex:
        rerun = pd.DataFrame(
            list(ex.map(_fault_job, zip(rows.planner, rows.seed, strict=True))),
            columns=["planner", "seed", "faults_fired", "term", "sci", "energy"],
        )
    m = rerun.merge(
        rows[["planner", "seed", "termination", "science_return", "energy_spent", "success"]],
        on=["planner", "seed"],
    )
    reproduced = float(
        (
            (m.term == m.termination)
            & ((m.sci - m.science_return).abs() < 1e-9)
            & ((m.energy - m.energy_spent).abs() < 1e-6)
        ).mean()
    )
    fired_share = m.assign(any=m.faults_fired > 0).groupby("planner")["any"].mean()
    a = m[m.planner == "adaptive_risk_aware_astar"].set_index("seed")
    f = m[m.planner == "risk_aware_astar"].set_index("seed")
    disc = a.success != f.success
    both = (a.faults_fired > 0) & (f.faults_fired > 0)
    none = (a.faults_fired == 0) & (f.faults_fired == 0)
    stats = {
        "Reproduced": reproduced,
        "FiredAdaptive": float(fired_share["adaptive_risk_aware_astar"]),
        "FiredFixed": float(fired_share["risk_aware_astar"]),
        "FiredAstar": float(fired_share["astar"]),
        "MedianSteps": float(rows.steps.median()),
        "Horizon": int(rows.max_steps.iloc[0]),
        "Discordant": int(disc.sum()),
        "DiscordantBoth": int((disc & both).sum()),
        "DiscordantNone": int((disc & none).sum()),
        "DiscordantMixed": int((disc & ~both & ~none).sum()),
    }
    return m, stats


def _calibration_job(args):
    seed, corrected = args
    if corrected:

        def ingest(self, record):
            k = int(record.terrain_class)
            adjusted = float(np.clip(record.slip - 0.01 * record.slope, 0.0, 1.0))
            self.class_belief[k].update(
                adjusted, obs_variance=self.aleatoric_sd[k] ** 2 + W.SLIP_OBS_VARIANCE
            )
            self._invalidate()

        W.AdaptiveWorldModel.ingest_slip = ingest
    r = run_mission(
        MissionConfig(
            body="mars",
            planner="adaptive_risk_aware_astar",
            size=48,
            n_targets=4,
            max_steps=500,
            solar_rate=2.0,
        ),
        seed=seed,
    )
    out = []
    for k, b in r.belief_snapshot.items():
        if b["n_observations"] >= 1:
            truth = TRUE_CLASS_PARAMS["mars"][int(k)].slip_mean
            out.append(
                (corrected, seed, int(k), b["n_observations"], b["mean"], b["epistemic_sd"], truth)
            )
    return out


def learner_calibration() -> tuple[pd.DataFrame, dict]:
    jobs = [(s, c) for c in (False, True) for s in VALIDATION_SEEDS]
    # a fresh process per job, so the corrected rule never leaks into the
    # committed-rule runs through a patched class in a reused worker
    with ProcessPoolExecutor(max_tasks_per_child=1) as ex:
        rows = [x for chunk in ex.map(_calibration_job, jobs) for x in chunk]
    df = pd.DataFrame(rows, columns=["corrected", "seed", "cls", "n", "mean", "sd", "truth"])
    df["covered"] = (df["mean"] - df["truth"]).abs() <= 1.96 * df["sd"]
    df["abs_error"] = (df["mean"] - df["truth"]).abs()
    stats = {}
    for flag, name in ((False, "Committed"), (True, "Corrected")):
        sub = df[df.corrected == flag]
        stats[f"Coverage{name}"] = float(sub.covered.mean())
        stats[f"MedianError{name}"] = float(sub.abs_error.median())
        stats[f"MedianSd{name}"] = float(sub.sd.median())
    stats["CalibrationMissions"] = len(VALIDATION_SEEDS)
    return df, stats


def main() -> None:
    faults, f = fault_exposure()
    faults.to_csv(RESULTS / "audit_fault_exposure.csv", index=False)
    calib, c = learner_calibration()
    calib.to_csv(RESULTS / "audit_learner_calibration.csv", index=False)

    def pct(x):
        return f"{100 * x:.0f}\\%"

    lines = [
        "% AUTO-GENERATED by scripts/audit_confirmatory.py - post-hoc audits, not confirmatory",
        rf"\newcommand{{\AuditReproduced}}{{{pct(f['Reproduced'])}}}",
        rf"\newcommand{{\AuditFiredAdaptive}}{{{pct(f['FiredAdaptive'])}}}",
        rf"\newcommand{{\AuditFiredFixed}}{{{pct(f['FiredFixed'])}}}",
        rf"\newcommand{{\AuditFiredAstar}}{{{pct(f['FiredAstar'])}}}",
        rf"\newcommand{{\AuditMedianSteps}}{{{f['MedianSteps']:.0f}}}",
        rf"\newcommand{{\AuditHorizon}}{{{f['Horizon']}}}",
        rf"\newcommand{{\AuditDiscordant}}{{{f['Discordant']}}}",
        rf"\newcommand{{\AuditDiscordantBoth}}{{{f['DiscordantBoth']}}}",
        rf"\newcommand{{\AuditDiscordantNone}}{{{f['DiscordantNone']}}}",
        rf"\newcommand{{\AuditDiscordantMixed}}{{{f['DiscordantMixed']}}}",
        rf"\newcommand{{\AuditCoverageCommitted}}{{{c['CoverageCommitted']:.2f}}}",
        rf"\newcommand{{\AuditCoverageCorrected}}{{{c['CoverageCorrected']:.2f}}}",
        rf"\newcommand{{\AuditErrorCommitted}}{{{c['MedianErrorCommitted']:.3f}}}",
        rf"\newcommand{{\AuditErrorCorrected}}{{{c['MedianErrorCorrected']:.3f}}}",
        rf"\newcommand{{\AuditSdCommitted}}{{{c['MedianSdCommitted']:.4f}}}",
        rf"\newcommand{{\AuditCalibrationMissions}}{{{c['CalibrationMissions']}}}",
    ]
    MACROS.write_text("\n".join(lines) + "\n")
    print(json.dumps({**f, **c}, indent=2))


if __name__ == "__main__":
    main()

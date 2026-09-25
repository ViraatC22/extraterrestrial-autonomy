"""Exploratory comparison of engine v1 and v2 on VALIDATION seeds.

Not a confirmatory study. It runs the confirmatory design (same conditions,
mission size and planners) on validation seeds under both engines, to see
whether the v2 fixes change the picture before any v2 study is declared.
Validation seeds are the ones the protocol reserves for exactly this kind of
exploration; no test or OOD seed is touched.

    python scripts/explore_v2.py [n_seeds]
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from exonaut.experiments.io import save_results
from exonaut.experiments.protocol import load_splits
from exonaut.experiments.provenance import environment_record
from exonaut.simulation import MissionConfig, run_mission

RESULTS = Path(__file__).resolve().parents[1] / "data" / "results"
META = json.loads((RESULTS / "exonaut_main.metadata.json").read_text())
PLANNERS = ["astar", "risk_aware_astar", "adaptive_risk_aware_astar"]
ENGINES = ["v1", "v2"]


def _job(args):
    engine, cond, planner, seed = args
    config = MissionConfig(
        **{
            **META["base_config"],
            "body": cond["body"],
            "planner": planner,
            "prior_body": cond.get("prior_body", "moon"),
            **cond.get("overrides", {}),
            "engine": engine,
        }
    )
    r = run_mission(config, seed=seed, collect_history=True)
    row = r.to_row()
    row.update(
        {
            "condition": cond["name"],
            "split": "validation",
            "engine": engine,
            "faults_fired": sum(len(f["faults"]) for f in r.history),
        }
    )
    for k, b in r.belief_snapshot.items():
        row[f"belief_class{k}"] = b["mean"]
        row[f"belief_sd_class{k}"] = b["epistemic_sd"]
        row[f"belief_n_class{k}"] = b["n_observations"]
    return row


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    seeds = list(load_splits().get("validation"))[:n]
    jobs = [
        (e, c, p, s) for e in ENGINES for c in META["conditions"] for p in PLANNERS for s in seeds
    ]
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(_job, jobs, chunksize=4))
    df = pd.DataFrame(rows)
    design = {
        "engines": ENGINES,
        "planners": PLANNERS,
        "conditions": META["conditions"],
        "base_config": META["base_config"],
        "seeds": seeds,
        "split": "validation",
    }
    meta = {
        **environment_record("exonaut-explore-v2-validation", design),
        **design,
        "status": "EXPLORATORY - validation seeds only; not confirmatory evidence",
    }
    written = save_results(df, "exploration_v2_validation", meta)
    print(f"{len(df)} missions -> {written['csv']}")


if __name__ == "__main__":
    main()

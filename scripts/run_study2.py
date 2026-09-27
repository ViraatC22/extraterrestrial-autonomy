"""Run Study 2 exactly as frozen, once. Or dry-run it on validation seeds.

    python scripts/run_study2.py --dry-run      # validation seeds; no authorization needed
    python scripts/run_study2.py                # the confirmatory run (see below)

The confirmatory run needs, and checks:
  - docs/PREREGISTRATION_V2.md exists and EXONAUT_AUTHORIZE_V2_CONFIRMATORY holds its
    SHA-256 (the terrain generator also enforces this for every seed);
  - the design file's digest equals the one recorded in that plan;
  - a clean git worktree (the commit is recorded in the metadata);
  - no existing Study 2 results (it refuses to overwrite).

Seeds: the first n of each condition's pool in data/splits/v2/seed_manifest.json.
Every row carries the columns in RESULT_COLUMNS, and nothing else - the schema
the plan freezes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "experiments" / "configs" / "study2.json"
RESULTS = ROOT / "data" / "results"
DRY_RUN_DIR = ROOT / "data" / "validation" / "study2_dry_run"
DRY_RUN_SEEDS = 20

RESULT_COLUMNS = [
    "condition",
    "role",
    "body",
    "planner",
    "seed",
    "termination",
    "success",
    "science_return",
    "science_possible",
    "science_fraction",
    "targets_visited",
    "targets_total",
    "energy_spent",
    "energy_generated",
    "min_charge",
    "steps",
    "distance_travelled",
    "interventions",
    "severe_slip_events",
    "mean_slip",
    "hazard_refusals",
    "final_distance_from_home",
    "calibration_records",
    "calibration_hits95",
    "severe_predicted_sum",
    "severe_observed",
    "prediction_steps",
    "engine",
    "class_assignment",
    "epistemic_scale",
]


def design_digest(design: dict) -> str:
    from exonaut.experiments.provenance import design_digest as digest

    return digest(design)


def seeds_for(design: dict, dry_run: bool) -> dict[str, list[int]]:
    from exonaut.experiments.v2_protocol import check_development_seeds, load_manifest

    if dry_run:
        seeds = list(range(200_000, 200_000 + DRY_RUN_SEEDS))
        check_development_seeds(seeds, "validation")
        return {c["name"]: seeds for c in design["conditions"]}
    manifest = load_manifest()
    return {
        c["name"]: manifest["splits"][c["pool"]][: design["n_seeds"]] for c in design["conditions"]
    }


def _job(args):
    condition, planner, seed, base = args
    from scipy.stats import norm

    from exonaut.environments import TRUE_CLASS_PARAMS
    from exonaut.simulation import MissionConfig, run_mission

    config = MissionConfig(
        **{**base, "body": condition["body"], "planner": planner, **condition.get("overrides", {})}
    )
    r = run_mission(config, seed=int(seed), collect_history=True)
    truth = TRUE_CLASS_PARAMS[condition["body"]]
    z95 = float(norm.ppf(0.975))
    records = hits = 0
    for d in r.decisions:
        for k, b in d["class_belief"].items():
            if b["n_observations"] >= 1 and b["epistemic_sd"] > 0:
                records += 1
                hits += abs(b["mean"] - truth[int(k)].slip_mean) <= z95 * b["epistemic_sd"]
    predicted = observed = steps = 0.0
    for f in r.history:
        p = f.get("prediction")
        if p and f["reason"] not in ("hazard_refused", "off_map", "insufficient_energy"):
            steps += 1
            predicted += p["p_severe"]
            observed += f["slip"] >= 0.8
    return {
        "condition": condition["name"],
        "role": condition["role"],
        "body": condition["body"],
        "planner": planner,
        "seed": int(seed),
        "termination": r.termination,
        "success": bool(r.success),
        "science_return": r.science_return,
        "science_possible": r.science_possible,
        "science_fraction": r.science_return / max(r.science_possible, 1e-9),
        "targets_visited": r.targets_visited,
        "targets_total": r.targets_total,
        "energy_spent": r.energy_spent,
        "energy_generated": r.energy_generated,
        "min_charge": r.min_charge,
        "steps": r.steps,
        "distance_travelled": r.distance_travelled,
        "interventions": r.interventions,
        "severe_slip_events": r.severe_slip_events,
        "mean_slip": r.mean_slip,
        "hazard_refusals": r.hazard_refusals,
        "final_distance_from_home": r.final_distance_from_home,
        "calibration_records": records,
        "calibration_hits95": int(hits),
        "severe_predicted_sum": predicted,
        "severe_observed": int(observed),
        "prediction_steps": int(steps),
        "engine": config.engine,
        "class_assignment": config.class_assignment,
        "epistemic_scale": config.epistemic_scale,
    }


def check_authorized_run(design: dict) -> dict:
    """Every precondition of the confirmatory run; raises with the reason."""
    import subprocess

    from exonaut.experiments.v2_protocol import PREREGISTRATION_V2, authorized

    if not PREREGISTRATION_V2.exists():
        raise SystemExit("docs/PREREGISTRATION_V2.md does not exist: Study 2 is not frozen.")
    if not authorized():
        raise SystemExit(
            "not authorized: set EXONAUT_AUTHORIZE_V2_CONFIRMATORY to the plan's SHA-256."
        )
    recorded = re.search(r"Design digest: `([0-9a-f]+)`", PREREGISTRATION_V2.read_text())
    if not recorded or recorded.group(1) != design_digest(design):
        raise SystemExit("the design file does not match the digest recorded in the plan.")
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    )
    if status.stdout.strip():
        raise SystemExit("the git worktree is not clean; commit before the confirmatory run.")
    if (RESULTS / f"{design['output']}.csv").exists():
        raise SystemExit("Study 2 results already exist; refusing to overwrite.")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return {
        "commit": commit.stdout.strip(),
        "plan_sha256": hashlib.sha256(PREREGISTRATION_V2.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    design = json.loads(DESIGN.read_text())
    provenance = {} if args.dry_run else check_authorized_run(design)
    seeds = seeds_for(design, args.dry_run)
    jobs = [
        (c, p, s, design["base_config"])
        for c in design["conditions"]
        for p in design["planners"]
        for s in seeds[c["name"]]
    ]
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(_job, jobs, chunksize=2))
    frame = pd.DataFrame(rows)[RESULT_COLUMNS]
    out_dir = DRY_RUN_DIR if args.dry_run else RESULTS
    out_dir.mkdir(parents=True, exist_ok=True)
    name = "study2_dry_run" if args.dry_run else design["output"]
    frame.to_csv(out_dir / f"{name}.csv", index=False)
    import scipy

    meta = {
        "study": "Study 2 DRY RUN (validation seeds)" if args.dry_run else "Study 2",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "design_file": str(DESIGN.relative_to(ROOT)),
        "design_digest": design_digest(design),
        "n_missions": len(frame),
        "platform": platform.platform(),
        "software": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "python": platform.python_version(),
        },
        **provenance,
    }
    (out_dir / f"{name}.metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"{len(frame)} missions -> {out_dir / name}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())

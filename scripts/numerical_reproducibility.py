"""Cross-platform numerical reproducibility of the Study 2 engine. VALIDATION seeds only.

    python scripts/numerical_reproducibility.py run --tag macos_arm64 [--label baseline]
    python scripts/numerical_reproducibility.py compare --a macos_arm64 --b linux_x86_64 [--label baseline]

`run` executes the Study 2 configuration (engine v2, confusion-aware learner
M3) for both planners on every validation seed, on both bodies, and records
per mission: the outcome, fingerprints of the generated terrain (exact bytes,
and discrete class/hazard only), the full driven path, and every decision's
selected target and P(fail) as exact hex floats. The Linux run happens in the
GitHub workflow "numerical reproducibility (Linux)".

`compare` finds, for every mission that differs between two platforms, the
first place it differs - terrain, a decision value, a decision choice, or the
path - and summarises it, with the primary effect estimate computed on each
platform. Output: data/validation/numerics/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from exonaut.experiments.v2_protocol import check_development_seeds

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "validation" / "numerics"
META = json.loads((ROOT / "data/results/exonaut_main.metadata.json").read_text())
VALIDATION_SEEDS = list(range(200_000, 200_200))
SEED_USE = {"validation": VALIDATION_SEEDS}
PLANNERS = ("risk_aware_astar", "adaptive_risk_aware_astar")
#: the Study 2 configuration chosen by the project owner (calibration option A, M3)
STUDY2 = {"engine": "v2", "class_assignment": "responsibility", "prior_body": "moon"}


def _digest(*arrays) -> str:
    h = hashlib.sha256()
    for a in arrays:
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()[:16]


def _job(args):
    body, seed, planner = args
    from exonaut.environments import canonicalize, make_environment
    from exonaut.simulation import MissionConfig, run_mission

    config = MissionConfig(**{**META["base_config"], **STUDY2, "body": body, "planner": planner})
    # the terrain the v2 engine actually uses
    t = canonicalize(make_environment(body, seed=seed, size=config.size))
    r = run_mission(config, seed=seed, collect_history=True)
    decisions = [
        {
            "step": d["step"],
            "reason": d["reason"],
            "selected": next((c["target_id"] for c in d["candidates"] if c.get("selected")), None),
            "p": [float(c["p_failure"]).hex() for c in d["candidates"] if c.get("reachable")],
        }
        for d in r.decisions
    ]
    return {
        "body": body,
        "seed": seed,
        "planner": planner,
        "terrain_exact": _digest(t.elevation, t.slope, t.roughness, t.illumination),
        "terrain_discrete": _digest(t.terrain_class, t.hazard),
        "termination": r.termination,
        "success": bool(r.success),
        "science_fraction": r.science_return / max(r.science_possible, 1e-9),
        "energy_spent": float(r.energy_spent).hex(),
        "steps": r.steps,
        "path": ";".join(f"{f['row']},{f['col']}" for f in r.history),
        "decisions": json.dumps(decisions),
    }


def run(tag: str, label: str) -> None:
    import platform

    check_development_seeds(VALIDATION_SEEDS, "validation")
    jobs = [(b, s, p) for b in ("mars", "moon") for s in VALIDATION_SEEDS for p in PLANNERS]
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(_job, jobs, chunksize=2))
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / f"{label}_{tag}.csv.gz", index=False)
    (OUT / f"{label}_{tag}.platform.json").write_text(
        json.dumps({"platform": platform.platform(), "machine": platform.machine()}, indent=2)
        + "\n"
    )
    print(f"{len(rows)} missions written for {label}/{tag}")


def first_difference(x: pd.Series, y: pd.Series) -> str:
    if x.terrain_discrete != y.terrain_discrete:
        return "terrain_discrete"
    dx, dy = json.loads(x.decisions), json.loads(y.decisions)
    for a, b in zip(dx, dy, strict=False):
        if a["selected"] != b["selected"] or a["reason"] != b["reason"]:
            return "decision_choice"
        if a["p"] != b["p"]:
            # values differ; did the choice survive? keep looking for a choice change
            continue
    if len(dx) != len(dy):
        return "decision_count"
    if x.path != y.path:
        return "path_only"
    if x.energy_spent != y.energy_spent:
        return "energy_value_only"
    return "none"


def first_value_difference(x: pd.Series, y: pd.Series) -> int | None:
    """Index of the first decision whose P(fail) values differ in any bit."""
    dx, dy = json.loads(x.decisions), json.loads(y.decisions)
    for i, (a, b) in enumerate(zip(dx, dy, strict=False)):
        if a["p"] != b["p"]:
            return i
    return None


def effect(frame: pd.DataFrame, body: str) -> dict:
    g = frame[frame.body == body].pivot_table(index="seed", columns="planner", values="success")
    a = g["adaptive_risk_aware_astar"].astype(bool)
    f = g["risk_aware_astar"].astype(bool)
    return {
        "success_adaptive": float(a.mean()),
        "success_fixed": float(f.mean()),
        "delta": float(a.mean() - f.mean()),
        "only_adaptive": int((a & ~f).sum()),
        "only_fixed": int((~a & f).sum()),
    }


def compare(tag_a: str, tag_b: str, label: str) -> dict:
    a = pd.read_csv(OUT / f"{label}_{tag_a}.csv.gz")
    b = pd.read_csv(OUT / f"{label}_{tag_b}.csv.gz")
    keys = ["body", "seed", "planner"]
    m = a.merge(b, on=keys, suffixes=("_a", "_b"))
    rows = []
    for _, r in m.iterrows():
        x = pd.Series({k[:-2]: r[k] for k in r.index if k.endswith("_a")})
        y = pd.Series({k[:-2]: r[k] for k in r.index if k.endswith("_b")})
        rows.append(
            {
                **{k: r[k] for k in keys},
                "terrain_exact_same": x.terrain_exact == y.terrain_exact,
                "terrain_discrete_same": x.terrain_discrete == y.terrain_discrete,
                "outcome_same": x.termination == y.termination and x.success == y.success,
                "success_same": x.success == y.success,
                "path_same": x.path == y.path,
                "identical": x.path == y.path
                and x.decisions == y.decisions
                and x.energy_spent == y.energy_spent,
                "first_difference": first_difference(x, y),
                "first_value_difference_decision": first_value_difference(x, y),
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv(OUT / f"{label}_comparison.csv", index=False)
    summary = {
        "label": label,
        "platforms": [tag_a, tag_b],
        "missions": len(table),
        "terrain_bytes_identical": int(table.terrain_exact_same.sum()),
        "terrain_discrete_identical": int(table.terrain_discrete_same.sum()),
        "fully_identical": int(table.identical.sum()),
        "same_path": int(table.path_same.sum()),
        "same_outcome": int(table.outcome_same.sum()),
        "success_flipped": int((~table.success_same).sum()),
        "first_difference_counts": table.first_difference.value_counts().to_dict(),
        "effect": {
            body: {tag_a: effect(a, body), tag_b: effect(b, body)} for body in ("mars", "moon")
        },
    }
    (OUT / f"{label}_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["run", "compare"])
    parser.add_argument("--tag")
    parser.add_argument("--a")
    parser.add_argument("--b")
    parser.add_argument("--label", default="baseline")
    args = parser.parse_args()
    if args.phase == "run":
        run(args.tag, args.label)
    else:
        compare(args.a, args.b, args.label)

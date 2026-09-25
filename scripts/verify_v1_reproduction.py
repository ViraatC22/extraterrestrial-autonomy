"""Re-run every committed confirmatory mission and check it reproduces exactly.

The confirmatory results were produced by the v1 engine. Later work (the
interface, the v2 fixes) must not change what v1 does. This script is the
check: it re-runs all rows of data/results/exonaut_main.csv with the default
engine and compares termination, science and energy to the committed values.

    python scripts/verify_v1_reproduction.py
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from exonaut.simulation import MissionConfig, run_mission

RESULTS = Path(__file__).resolve().parents[1] / "data" / "results"
META = json.loads((RESULTS / "exonaut_main.metadata.json").read_text())
CONDITIONS = {c["name"]: c for c in META["conditions"]}


def _run(row: dict) -> tuple[int, str, bool]:
    cond = CONDITIONS[row["condition"]]
    config = MissionConfig(
        **{
            **META["base_config"],
            "body": cond["body"],
            "planner": row["planner"],
            "prior_body": cond.get("prior_body", "moon"),
            **cond.get("overrides", {}),
        }
    )
    assert config.engine == "v1"
    r = run_mission(config, seed=int(row["seed"]))
    same = (
        r.termination == row["termination"]
        and abs(r.science_return - row["science_return"]) < 1e-9
        and abs(r.energy_spent - row["energy_spent"]) < 1e-6
        and r.steps == row["steps"]
    )
    return int(row["seed"]), row["planner"], same


def main() -> int:
    rows = pd.read_csv(RESULTS / "exonaut_main.csv").to_dict(orient="records")
    with ProcessPoolExecutor() as ex:
        results = list(ex.map(_run, rows, chunksize=4))
    bad = [(s, p) for s, p, ok in results if not ok]
    print(f"{len(results) - len(bad)}/{len(results)} committed missions reproduce exactly")
    for seed, planner in bad[:20]:
        print("  MISMATCH", seed, planner)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

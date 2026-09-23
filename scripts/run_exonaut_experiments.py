"""Run the preregistered EXONAUT experiment on frozen seed splits.

Examples:
    python scripts/run_exonaut_experiments.py --pilot
    python scripts/run_exonaut_experiments.py --config experiments/configs/exonaut_main.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from exonaut.experiments.mission_runner import ExperimentCondition, run_mission_sweep

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_config(path: Path) -> dict:
    payload = json.loads(path.read_text())
    payload["conditions"] = tuple(
        ExperimentCondition(**condition)
        for condition in payload["conditions"]
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true",
                        help="use experiments/configs/exonaut_pilot.json")
    parser.add_argument("--config", type=Path,
                        help="JSON experiment configuration; defaults to exonaut_main.json")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--output", help="override the configured output filename")
    args = parser.parse_args()

    if args.pilot and args.config:
        parser.error("--pilot and --config are mutually exclusive")
    config_path = args.config or PROJECT_ROOT / "experiments" / "configs" / (
        "exonaut_pilot.json" if args.pilot else "exonaut_main.json"
    )
    config = load_config(config_path)

    run_mission_sweep(
        planners=tuple(config["planners"]),
        conditions=config["conditions"],
        n_seeds=int(config["n_seeds"]),
        base_config=config["base_config"],
        save_as=args.output or config["output"],
        n_workers=args.workers,
    )


if __name__ == "__main__":
    main()

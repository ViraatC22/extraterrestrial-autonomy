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
    """Load a YAML or JSON experiment config.

    YAML is the documented format because a config is meant to be read and
    edited by a person; JSON is still accepted so older designs stay runnable.
    """
    text = path.read_text()
    if path.suffix in {".yaml", ".yml"}:
        import yaml

        payload = yaml.safe_load(text)
    else:
        payload = json.loads(text)
    payload["conditions"] = tuple(
        ExperimentCondition(**condition) for condition in payload["conditions"]
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pilot", action="store_true", help="use experiments/configs/exonaut_pilot.json"
    )
    parser.add_argument(
        "--config", type=Path, help="JSON experiment configuration; defaults to exonaut_main.json"
    )
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--output", help="override the configured output filename")
    args = parser.parse_args()

    if args.pilot and args.config:
        parser.error("--pilot and --config are mutually exclusive")
    default_name = "exonaut_pilot" if args.pilot else "exonaut_main"
    config_path = args.config
    if config_path is None:
        for candidate in (
            PROJECT_ROOT / "configs" / f"{default_name}.yaml",
            PROJECT_ROOT / "experiments" / "configs" / f"{default_name}.json",
        ):
            if candidate.exists():
                config_path = candidate
                break
        else:
            parser.error(f"no config found for {default_name}")
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

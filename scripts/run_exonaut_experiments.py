"""Run the preregistered EXONAUT experiment on frozen seed splits.

Examples:
    python scripts/run_exonaut_experiments.py --pilot
    python scripts/run_exonaut_experiments.py --seeds 50 --workers 8
"""
from __future__ import annotations

import argparse

from exonaut.experiments.mission_runner import run_mission_sweep


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true",
                        help="run 4 seeds/condition on a smaller, shorter mission")
    parser.add_argument("--seeds", type=int, default=50,
                        help="reserved seeds per condition for the full run")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--output", default="exonaut_main.csv")
    args = parser.parse_args()

    if args.pilot:
        n_seeds = 4
        base = {"size": 32, "n_targets": 3, "max_steps": 180}
        output = "exonaut_pilot.csv" if args.output == "exonaut_main.csv" else args.output
    else:
        n_seeds = args.seeds
        base = {"size": 64, "n_targets": 5, "max_steps": 600}
        output = args.output

    run_mission_sweep(
        n_seeds=n_seeds,
        base_config=base,
        save_as=output,
        n_workers=args.workers,
    )


if __name__ == "__main__":
    main()

"""Calibrate world-model priors from TRAIN-split terrains only.

The robot's initial beliefs must come from somewhere defensible. Here they
come from noisy slip measurements taken on training terrains of each body -
never from ground-truth class parameters, and never from validation, test or
OOD seeds.

    python scripts/calibrate_priors.py
"""
from __future__ import annotations

from exonaut.autonomy.priors import calibrate_prior, save_prior
from exonaut.environments import BODIES
from exonaut.experiments.protocol import load_splits

N_CALIBRATION_SEEDS = 60


def main() -> None:
    splits = load_splits()
    train_seeds = splits.get("train")[:N_CALIBRATION_SEEDS]
    print(f"calibrating from {len(train_seeds)} TRAIN seeds "
          f"[{train_seeds[0]}..{train_seeds[-1]}]")

    for body in BODIES:
        prior = calibrate_prior(body, train_seeds)
        path = save_prior(prior, train_seeds)
        print(f"\n{body}: -> {path}")
        for klass, (mean, variance) in sorted(prior["means"].items()):
            print(f"  class {klass}: mean slip {mean:.3f} "
                  f"(prior sd {variance ** 0.5:.3f}, "
                  f"aleatoric sd {prior['aleatoric_sd'][klass]:.3f}, "
                  f"n={prior['counts'][klass]})")


if __name__ == "__main__":
    main()

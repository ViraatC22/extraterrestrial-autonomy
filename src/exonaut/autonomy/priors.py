"""Where the robot's initial beliefs come from.

This matters for the integrity of the whole comparison. If the prior were
simply hand-written to be wrong in a way that only an adaptive planner could
repair, the headline result would be an artifact of that choice rather than a
finding.

So the prior is *calibrated*, from TRAIN-split terrains of the prior body
only, using the same measurement channel the robot has - noisy slip samples,
not ground truth. That is exactly what a mission would do: characterize
terrain from the experience you already have, then fly.

The out-of-distribution test then does the honest thing: it keeps that
lunar-calibrated prior and sends the robot to Mars, where the same class
names carry different statistics. Nobody rigged the prior; it is simply
correct about the wrong world, which is the situation adaptive autonomy is
supposed to handle.

Calibrated priors are cached to data/processed/ so every run uses the same
numbers, and the cache records which seeds produced it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..environments import N_TERRAIN_CLASSES, make_environment

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = PROJECT_ROOT / "data" / "processed"

# Widening applied to the calibrated variance so the prior expresses genuine
# uncertainty about a *new* site rather than false confidence from having
# characterized a handful of maps.
PRIOR_VARIANCE_INFLATION = 4.0
MIN_PRIOR_VARIANCE = 0.004


def calibrate_prior(
    body: str, seeds, size: int = 64, samples_per_seed: int = 400, rng_seed: int = 12345
) -> dict:
    """Estimate per-class slip statistics by sampling noisy measurements.

    Samples are drawn the way the robot would get them - one noisy slip
    reading per visited cell - rather than by reading class parameters
    directly, so the prior inherits realistic measurement error.
    """
    rng = np.random.default_rng(rng_seed)
    sums = np.zeros(N_TERRAIN_CLASSES)
    sum_squares = np.zeros(N_TERRAIN_CLASSES)
    counts = np.zeros(N_TERRAIN_CLASSES)

    for seed in seeds:
        terrain = make_environment(body, seed=int(seed), size=size)
        rows = rng.integers(0, size, samples_per_seed)
        cols = rng.integers(0, size, samples_per_seed)
        for r, c in zip(rows, cols, strict=False):
            if terrain.hazard[r, c]:
                continue
            klass = int(terrain.terrain_class[r, c])
            mean, dispersion = terrain.true_slip_distribution(int(r), int(c))
            # subtract the slope contribution: the prior is about the class
            slope_adjusted = mean - 0.01 * float(terrain.slope[r, c])
            sample = float(np.clip(rng.normal(slope_adjusted, max(dispersion, 1e-6)), 0.0, 1.0))
            sums[klass] += sample
            sum_squares[klass] += sample**2
            counts[klass] += 1

    means, aleatoric, variances = {}, {}, {}
    for klass in range(N_TERRAIN_CLASSES):
        n = counts[klass]
        if n < 2:
            # class never encountered during calibration: stay deliberately
            # uncertain rather than guessing precisely
            means[klass] = 0.25
            variances[klass] = 0.05
            aleatoric[klass] = 0.15
            continue
        mean = sums[klass] / n
        variance = max(sum_squares[klass] / n - mean**2, 1e-6)
        means[klass] = float(mean)
        aleatoric[klass] = float(np.sqrt(variance))
        # uncertainty in the *mean*, inflated for site-to-site variation
        variances[klass] = float(max(PRIOR_VARIANCE_INFLATION * variance / n, MIN_PRIOR_VARIANCE))

    return {
        "body": body,
        "n_seeds": len(list(seeds)),
        "samples_per_seed": samples_per_seed,
        "means": {k: (means[k], variances[k]) for k in range(N_TERRAIN_CLASSES)},
        "aleatoric_sd": aleatoric,
        "counts": {k: int(counts[k]) for k in range(N_TERRAIN_CLASSES)},
    }


def _cache_path(body: str) -> Path:
    return CACHE_DIR / f"prior_{body}.json"


def save_prior(prior: dict, seeds) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(prior)
    payload["means"] = {str(k): list(v) for k, v in prior["means"].items()}
    payload["aleatoric_sd"] = {str(k): v for k, v in prior["aleatoric_sd"].items()}
    payload["counts"] = {str(k): v for k, v in prior["counts"].items()}
    payload["calibration_seeds"] = [int(s) for s in seeds]
    path = _cache_path(prior["body"])
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_prior(body: str) -> dict:
    path = _cache_path(body)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run scripts/calibrate_priors.py so the prior "
            "is derived from TRAIN seeds rather than invented at runtime."
        )
    payload = json.loads(path.read_text())
    return {
        "body": payload["body"],
        "n_seeds": payload.get("n_seeds"),
        "means": {int(k): tuple(v) for k, v in payload["means"].items()},
        "aleatoric_sd": {int(k): v for k, v in payload["aleatoric_sd"].items()},
        "counts": {int(k): v for k, v in payload.get("counts", {}).items()},
        "calibration_seeds": payload.get("calibration_seeds", []),
    }


def default_prior(body: str) -> dict:
    return load_prior(body)

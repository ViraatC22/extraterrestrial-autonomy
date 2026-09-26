"""Seed manifest and access control for the planned v2 study (Study 2).

v2 confirmation must run on terrain nobody has seen. The v1 held-out splits
cannot guarantee that: 100 of their seeds were evaluated in Study 1, and until
2026-09-25 nothing recorded which other held-out seeds the interface displayed.
So v2 draws completely fresh confirmatory seeds from a range disjoint from
every v1 split, by a documented algorithm from a recorded master seed.

Development (calibration, power analysis, simulator validation) reuses the v1
train and validation splits, which were always development data.

Access control
--------------
`guard_seed` is called by the terrain generator itself (`make_environment`),
so no code path - API, script or notebook - can build a v2 confirmatory
terrain by accident. Every attempt, allowed or refused, is logged to the
held-out access log. Access is allowed only when BOTH hold:

  1. docs/PREREGISTRATION_V2.md exists (the plan has been frozen), and
  2. the environment variable EXONAUT_AUTHORIZE_V2_CONFIRMATORY is set to the
     SHA-256 of that file - so authorization names the exact plan it is for.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = PROJECT_ROOT / "data" / "splits" / "v2" / "seed_manifest.json"
PREREGISTRATION_V2 = PROJECT_ROOT / "docs" / "PREREGISTRATION_V2.md"
AUTH_ENV = "EXONAUT_AUTHORIZE_V2_CONFIRMATORY"

#: Recorded master seed and pool design (see build_manifest).
MASTER_SEED = 20260925
CONFIRMATORY_RANGE = (1_000_000, 100_000_000)
POOL_SIZE = 1000
DEVELOPMENT = ("train", "validation")
CONFIRMATORY = ("confirmatory_id", "confirmatory_ood")


class ConfirmatorySeedAccessError(PermissionError):
    """Raised when code tries to build a v2 confirmatory terrain unauthorized."""


def _checksum(lists: dict) -> str:
    blob = json.dumps({k: list(v) for k, v in sorted(lists.items())}, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def build_manifest() -> dict:
    """Deterministically construct the v2 manifest from the master seed.

    Confirmatory seeds: 2 x POOL_SIZE integers drawn without replacement,
    uniformly from CONFIRMATORY_RANGE, by numpy's default generator seeded
    with MASTER_SEED; the first POOL_SIZE (in draw order) are the in-
    distribution pool and the rest the out-of-distribution pool. A study uses
    the first n of a pool, in manifest order, for the n its plan fixes.
    """
    import numpy as np

    from .protocol import load_splits

    v1 = load_splits()
    low, high = CONFIRMATORY_RANGE
    rng = np.random.default_rng(MASTER_SEED)
    draw = rng.choice(high - low, size=2 * POOL_SIZE, replace=False) + low
    lists = {
        "train": [int(s) for s in v1.get("train", exclude_quarantined=False)],
        "validation": [int(s) for s in v1.get("validation", exclude_quarantined=False)],
        "confirmatory_id": [int(s) for s in draw[:POOL_SIZE]],
        "confirmatory_ood": [int(s) for s in draw[POOL_SIZE:]],
    }
    return {
        "version": "v2",
        "algorithm": (
            "train/validation: the v1 development splits, unchanged. confirmatory_id/_ood: "
            f"numpy.random.default_rng({MASTER_SEED}).choice({high - low}, size={2 * POOL_SIZE}, "
            f"replace=False) + {low}; first {POOL_SIZE} = confirmatory_id, next {POOL_SIZE} = "
            "confirmatory_ood. A study uses the first n of each pool in manifest order."
        ),
        "master_seed": MASTER_SEED,
        "confirmatory_range": list(CONFIRMATORY_RANGE),
        "splits": lists,
        "checksum": _checksum(lists),
    }


@lru_cache(maxsize=1)
def load_manifest() -> dict | None:
    if not MANIFEST_PATH.exists():
        return None
    manifest = json.loads(MANIFEST_PATH.read_text())
    if _checksum(manifest["splits"]) != manifest["checksum"]:
        raise ValueError("v2 seed manifest does not match its checksum")
    return manifest


@lru_cache(maxsize=1)
def _confirmatory_index() -> dict:
    manifest = load_manifest()
    if manifest is None:
        return {}
    return {seed: name for name in CONFIRMATORY for seed in manifest["splits"][name]}


def confirmatory_label(seed: int) -> str | None:
    """'confirmatory_id' / 'confirmatory_ood' for a v2 confirmatory seed, else None."""
    return _confirmatory_index().get(int(seed))


def authorized() -> bool:
    if not PREREGISTRATION_V2.exists():
        return False
    digest = hashlib.sha256(PREREGISTRATION_V2.read_bytes()).hexdigest()
    return os.environ.get(AUTH_ENV) == digest


def _log(seed: int, label: str, allowed: bool, purpose: str) -> None:
    from .access_log import heldout_log_path

    path = heldout_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": int(seed),
        "split": label,
        "endpoint": purpose,
        "allowed": allowed,
    }
    with path.open("a") as handle:
        handle.write(json.dumps(entry) + "\n")


def guard_seed(seed: int, purpose: str = "make_environment") -> None:
    """Refuse (and log) any unauthorized use of a v2 confirmatory seed."""
    label = confirmatory_label(seed)
    if label is None:
        return
    allowed = authorized()
    _log(seed, label, allowed, purpose)
    if not allowed:
        raise ConfirmatorySeedAccessError(
            f"seed {seed} is a v2 {label} seed. It may only be used after "
            "docs/PREREGISTRATION_V2.md is frozen and the run is authorized "
            f"({AUTH_ENV}=<sha256 of that file>)."
        )


def check_development_seeds(seeds, split: str) -> None:
    """Refuse any seed that is not in the named development split.

    Used by every script that develops the v2 method (calibration, power
    analysis): they may touch train and validation seeds only.
    """
    from .protocol import load_splits

    if split not in DEVELOPMENT:
        raise ValueError(f"development work may use train or validation only, not {split!r}")
    allowed = set(load_splits().get(split, exclude_quarantined=False))
    for seed in seeds:
        if int(seed) not in allowed or confirmatory_label(seed) is not None:
            raise ValueError(f"seed {seed} is not a {split} seed")

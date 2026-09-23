"""Immutable seed protocol.

The split files under `data/splits/` are the experimental equivalent of a
sealed envelope. They are written once, committed, and never regenerated;
`verify_splits()` recomputes their checksum so any later edit is detectable
rather than silent.

Why this exists: the proposed adaptive planner is *our* method, which creates
enormous pressure - conscious or not - to keep adjusting it until it wins. A
frozen split makes that structurally harder. Tuning happens on VALIDATION
seeds. TEST and OOD seeds are untouched until the analysis is run, once.

Split semantics
---------------
train      : RL training and prior calibration.
validation : hyperparameter and weight tuning for every method.
test       : in-distribution evaluation on the training body.
ood        : out-of-distribution evaluation (different body / shifted
             conditions). Never used for any tuning decision whatsoever.

The four sets are disjoint by construction and the constructor asserts it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SPLITS_DIR = PROJECT_ROOT / "data" / "splits"

SPLIT_NAMES = ("train", "validation", "test", "ood")

# Disjoint integer ranges, so even a regenerated split cannot accidentally
# overlap another.
SPLIT_RANGES = {
    "train":      (100_000, 200_000),
    "validation": (200_000, 300_000),
    "test":       (300_000, 400_000),
    "ood":        (400_000, 500_000),
}

DEFAULT_SIZES = {
    "train": 1000,
    "validation": 200,
    "test": 500,
    "ood": 500,
}


@dataclass(frozen=True)
class SeedSplits:
    train: tuple
    validation: tuple
    test: tuple
    ood: tuple
    created: str = ""
    note: str = ""
    _checksum: str = field(default="", repr=False)

    def __post_init__(self):
        sets = {name: set(getattr(self, name)) for name in SPLIT_NAMES}
        for a in SPLIT_NAMES:
            for b in SPLIT_NAMES:
                if a >= b:
                    continue
                overlap = sets[a] & sets[b]
                if overlap:
                    raise ValueError(
                        f"seed splits '{a}' and '{b}' overlap on {sorted(overlap)[:5]}"
                    )

    def get(self, name: str) -> tuple:
        if name not in SPLIT_NAMES:
            raise ValueError(f"unknown split {name!r}; expected one of {SPLIT_NAMES}")
        return getattr(self, name)

    def checksum(self) -> str:
        payload = json.dumps(
            {name: list(getattr(self, name)) for name in SPLIT_NAMES},
            sort_keys=True,
        ).encode()
        return hashlib.sha256(payload).hexdigest()


def build_splits(sizes: dict | None = None, note: str = "") -> SeedSplits:
    """Deterministically construct the splits from the fixed ranges.

    Deterministic rather than random: the split is reproducible from this
    function alone, so nobody has to trust that a one-off script was run
    honestly.
    """
    from datetime import date

    sizes = sizes or DEFAULT_SIZES
    values = {}
    for name in SPLIT_NAMES:
        low, high = SPLIT_RANGES[name]
        count = sizes[name]
        if low + count > high:
            raise ValueError(f"split {name} of size {count} exceeds its range")
        values[name] = tuple(range(low, low + count))
    return SeedSplits(created=date.today().isoformat(), note=note, **values)


def splits_path() -> Path:
    return SPLITS_DIR / "seed_splits.json"


def write_splits(splits: SeedSplits, overwrite: bool = False) -> Path:
    path = splits_path()
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"{path} already exists. The seed protocol is frozen by design; "
            "pass overwrite=True only if you intend to invalidate every "
            "result produced so far."
        )
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {name: list(getattr(splits, name)) for name in SPLIT_NAMES}
    payload["created"] = splits.created
    payload["note"] = splits.note
    payload["checksum"] = splits.checksum()
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_splits() -> SeedSplits:
    path = splits_path()
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run scripts/freeze_seed_protocol.py first; "
            "experiments must not invent their own seeds."
        )
    payload = json.loads(path.read_text())
    splits = SeedSplits(
        train=tuple(payload["train"]),
        validation=tuple(payload["validation"]),
        test=tuple(payload["test"]),
        ood=tuple(payload["ood"]),
        created=payload.get("created", ""),
        note=payload.get("note", ""),
    )
    recorded = payload.get("checksum")
    if recorded and recorded != splits.checksum():
        raise ValueError(
            "seed split checksum mismatch: data/splits/seed_splits.json has "
            "been modified since it was frozen. Every result derived from it "
            "is suspect."
        )
    return splits


def verify_splits() -> dict:
    """Check the frozen file is internally consistent. Used by the test
    suite so a tampered split fails CI rather than passing quietly."""
    splits = load_splits()
    return {
        "checksum": splits.checksum(),
        "created": splits.created,
        "sizes": {name: len(splits.get(name)) for name in SPLIT_NAMES},
        "disjoint": True,  # SeedSplits.__post_init__ raises otherwise
    }

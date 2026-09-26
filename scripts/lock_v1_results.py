"""Write the immutable lock for the v1 study (Study 1).

The v1 confirmatory results are a historical record: they were produced by
the v1 engine, including defects later documented, and must never be
overwritten, regenerated with changed code, or silently reinterpreted. This
script records what "v1" is - engine profile, the commit that generated the
results, the design and its digest, the seed-split checksum, and a SHA-256 of
every committed v1 artifact - in data/results/v1_LOCK.json.
`tests/test_v1_lock.py` fails if any locked file changes.

Run it once. Re-running refuses to overwrite an existing lock unless
--relock is given, which should only ever happen with a RESEARCH_LOG entry
explaining why.

    python scripts/lock_v1_results.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results"
LOCK = RESULTS / "v1_LOCK.json"

#: every artifact that constitutes the v1 study and its post-hoc audits
LOCKED = [
    "data/results/exonaut_main.csv",
    "data/results/exonaut_main.metadata.json",
    "data/results/exonaut_main_primary.csv",
    "data/results/exonaut_main_secondary.csv",
    "data/results/audit_fault_exposure.csv",
    "data/results/audit_learner_calibration.csv",
    "experiments/configs/exonaut_main.json",
    "data/splits/seed_splits.json",
    "data/splits/quarantine.json",
    "data/processed/prior_moon.json",
    "data/processed/prior_mars.json",
    "docs/PREREGISTRATION.md",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    from exonaut import __version__
    from exonaut.experiments.protocol import verify_splits
    from exonaut.experiments.provenance import design_digest, git_provenance

    if LOCK.exists() and "--relock" not in sys.argv:
        print(f"{LOCK} exists; refusing to overwrite (use --relock with a research-log entry)")
        return 1
    meta = json.loads((RESULTS / "exonaut_main.metadata.json").read_text())
    design = json.loads((ROOT / "experiments/configs/exonaut_main.json").read_text())
    splits = verify_splits()
    assert splits["checksum"] == meta["seed_split_checksum"], "split checksum changed since v1"
    reproduction = json.loads((RESULTS / "v1_reproduction.json").read_text())
    lock = {
        "study": "v1 (Study 1): confirmatory run, engine profile v1",
        "status": "IMMUTABLE - do not overwrite, regenerate, or reinterpret without a RESEARCH_LOG entry",
        "engine_profile": "v1",
        "engine_package_version_at_lock": __version__,
        "results_generated_utc": meta["generated_utc"],
        "results_generated_by_commit": meta["git"]["commit"],
        "results_generation_note": (
            "metadata lists data/results/exonaut_main.csv as the only dirty file: the results "
            "file was being written by the run itself"
        ),
        "design_config": "experiments/configs/exonaut_main.json",
        "design_digest": design_digest(design),
        "seed_split_checksum": meta["seed_split_checksum"],
        "n_missions": 750,
        "reproduction": reproduction,
        "locked_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "locked_at_commit": git_provenance().get("commit"),
        "sha256": {rel: sha256(ROOT / rel) for rel in LOCKED},
    }
    LOCK.write_text(json.dumps(lock, indent=2) + "\n")
    print(json.dumps({k: lock[k] for k in ("design_digest", "seed_split_checksum")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

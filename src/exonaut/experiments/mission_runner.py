"""Reproducible batch runner for the EXONAUT mission experiment.

Every planner is evaluated on the same mission seeds within each condition.
The seed split is loaded from the frozen protocol rather than synthesized by
the runner, and a metadata sidecar records the exact design and split checksum
used to create each CSV.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from ..planners import available_planners
from ..simulation import MissionConfig, run_mission
from .protocol import load_quarantine, load_splits

RESULTS_DIR = Path(__file__).resolve().parents[3] / "data" / "results"

DEFAULT_PLANNERS = (
    "astar",
    "risk_aware_astar",
    "adaptive_risk_aware_astar",
)


@dataclass(frozen=True)
class ExperimentCondition:
    """One matched experimental condition and its reserved seed split."""

    name: str
    split: str
    body: str
    prior_body: str = "moon"
    overrides: dict = field(default_factory=dict)

    def mission_kwargs(self) -> dict:
        return {
            "body": self.body,
            "prior_body": self.prior_body,
            **self.overrides,
        }


DEFAULT_CONDITIONS = (
    ExperimentCondition("moon_id", "test", "moon"),
    ExperimentCondition("mars_ood", "ood", "mars"),
    ExperimentCondition(
        "mars_high_uncertainty", "ood", "mars",
        overrides={"terrain_uncertainty": 1.5},
    ),
    ExperimentCondition(
        "mars_faults", "ood", "mars",
        overrides={"fault_rate": 1.0},
    ),
    ExperimentCondition(
        "mars_comm_delay", "ood", "mars",
        overrides={"comm_delay": 20},
    ),
)


def run_mission_trial(
    planner: str,
    condition: ExperimentCondition,
    seed: int,
    base_config: dict | None = None,
) -> dict:
    """Run one planner on one frozen-seed mission and return a flat row."""
    if planner not in available_planners():
        raise ValueError(f"unknown planner {planner!r}")
    config = MissionConfig(
        **(base_config or {}),
        **condition.mission_kwargs(),
        planner=planner,
    )
    row = run_mission(config, int(seed)).to_row()
    row["condition"] = condition.name
    row["split"] = condition.split
    return row


def _run_trial_star(args):
    return run_mission_trial(*args)


def _git_provenance() -> dict:
    """Commit the results were produced at, and whether the tree was dirty.

    A result that cannot be traced to an exact code state is not reproducible,
    and a dirty tree means the commit alone does not describe what ran.
    """
    root = Path(__file__).resolve().parents[3]
    def _git(*args):
        try:
            return subprocess.run(["git", "-C", str(root), *args],
                                  capture_output=True, text=True, timeout=10,
                                  check=True).stdout.strip()
        except Exception:
            return None
    dirty = _git("status", "--porcelain")
    return {
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty_worktree": bool(dirty) if dirty is not None else None,
        "dirty_files": sorted(line[3:] for line in dirty.splitlines())[:50] if dirty else [],
    }


def _software_versions() -> dict:
    import numpy
    import pandas
    import scipy
    return {
        "python": sys.version.split()[0],
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "scipy": scipy.__version__,
        "platform": platform.platform(),
    }


def _metadata(
    planners: tuple[str, ...],
    conditions: tuple[ExperimentCondition, ...],
    n_seeds: int,
    base_config: dict,
) -> dict:
    splits = load_splits()
    return {
        "schema_version": 1,
        "design": "matched randomized block",
        "planners": list(planners),
        "conditions": [asdict(c) for c in conditions],
        "n_seeds_per_condition": n_seeds,
        "base_config": base_config,
        "seed_split_checksum": splits.checksum(),
        "seed_split_created": splits.created,
        # Seeds excluded because they were observed before the protocol was
        # frozen. Recorded here so a reader can confirm which terrains the
        # confirmatory result did and did not see.
        "quarantined_seeds": {k: sorted(v) for k, v in load_quarantine().items()},
        "git": _git_provenance(),
        "software": _software_versions(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }


def run_mission_sweep(
    planners=DEFAULT_PLANNERS,
    conditions=DEFAULT_CONDITIONS,
    n_seeds: int = 50,
    base_config: dict | None = None,
    save_as: str | None = "exonaut_main.csv",
    n_workers: int | None = None,
    progress_cb=None,
) -> pd.DataFrame:
    """Evaluate planners on matched frozen seeds across all conditions."""
    planners = tuple(planners)
    conditions = tuple(conditions)
    base_config = dict(base_config or {})
    known = set(available_planners())
    unknown = set(planners) - known
    if unknown:
        raise ValueError(f"unknown planners: {sorted(unknown)}")
    if n_seeds < 1:
        raise ValueError("n_seeds must be positive")

    splits = load_splits()
    jobs = []
    for condition in conditions:
        seeds = splits.get(condition.split)
        if n_seeds > len(seeds):
            raise ValueError(
                f"requested {n_seeds} seeds from {condition.split}, "
                f"which contains only {len(seeds)}"
            )
        for seed in seeds[:n_seeds]:
            for planner in planners:
                jobs.append((planner, condition, int(seed), base_config))

    if n_workers is None:
        n_workers = max(1, (os.cpu_count() or 2) - 1)

    rows = []
    total = len(jobs)
    if n_workers == 1:
        for done, job in enumerate(jobs, start=1):
            rows.append(_run_trial_star(job))
            if progress_cb:
                progress_cb(done, total, job[0], job[1].name, job[2])
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futures = {pool.submit(_run_trial_star, job): job for job in jobs}
            for done, future in enumerate(as_completed(futures), start=1):
                rows.append(future.result())
                job = futures[future]
                if progress_cb:
                    progress_cb(done, total, job[0], job[1].name, job[2])
                elif done % 25 == 0 or done == total:
                    print(f"[{done}/{total}] EXONAUT missions complete")

    df = pd.DataFrame(rows).sort_values(
        ["condition", "planner", "seed"]
    ).reset_index(drop=True)

    if save_as:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        csv_path = RESULTS_DIR / save_as
        df.to_csv(csv_path, index=False)
        meta_path = csv_path.with_suffix(".metadata.json")
        meta_path.write_text(json.dumps(
            _metadata(planners, conditions, n_seeds, base_config),
            indent=2,
            sort_keys=True,
        ) + "\n")
        print(f"saved {len(df)} mission results to {csv_path}")
    return df

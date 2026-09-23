"""Run identity and environment capture.

Every experiment artifact carries a run ID and enough environment detail to
say what produced it. The run ID is derived from the design rather than from
the clock, so re-running an identical design produces an identical ID and a
changed design cannot silently overwrite an earlier result under the same
name.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def design_digest(payload: dict) -> str:
    """Stable 12-character digest of an experiment design."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def make_run_id(design_name: str, payload: dict) -> str:
    """`<design>-<digest>` - deterministic in the design, not the clock."""
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in design_name)
    return f"{safe}-{design_digest(payload)}"


def git_provenance() -> dict:
    """Commit the artifact was produced at, and whether the tree was dirty.

    A dirty tree means the commit alone does not describe what ran, so the
    changed paths are recorded too - that is what lets a reader check whether
    the difference could have affected the result.
    """

    def _git(*args):
        try:
            return subprocess.run(
                ["git", "-C", str(PROJECT_ROOT), *args],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            ).stdout.strip()
        except Exception:
            return None

    dirty = _git("status", "--porcelain")
    return {
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty_worktree": bool(dirty) if dirty is not None else None,
        "dirty_files": sorted(line[3:] for line in dirty.splitlines())[:50] if dirty else [],
    }


def software_versions() -> dict:
    import numpy
    import pandas
    import scipy

    versions = {
        "python": sys.version.split()[0],
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "scipy": scipy.__version__,
        "platform": platform.platform(),
    }
    for optional in ("torch", "sklearn", "statsmodels", "pyarrow"):
        with contextlib.suppress(Exception):
            versions[optional] = __import__(optional).__version__
    return versions


def environment_record(design_name: str, payload: dict) -> dict:
    return {
        "run_id": make_run_id(design_name, payload),
        "design_name": design_name,
        "design_digest": design_digest(payload),
        "generated_utc": datetime.now(UTC).isoformat(),
        "git": git_provenance(),
        "software": software_versions(),
    }

"""Where requests that expose held-out terrain are recorded.

A future confirmatory study has to show its seeds were untouched; this log is
the record. Tests redirect it with EXONAUT_HELDOUT_LOG so their deliberate
accesses never appear in the project's log.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def heldout_log_path() -> Path:
    default = PROJECT_ROOT / "data" / "splits" / "heldout_access_log.jsonl"
    return Path(os.environ.get("EXONAUT_HELDOUT_LOG", default))

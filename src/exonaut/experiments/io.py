"""Result persistence.

Results are written as Parquet (typed, compressed, the archival copy) with a
CSV alongside for inspection and for tools that cannot read Parquet. Both are
written from the same DataFrame in the same call, so they cannot drift.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

RESULTS_DIR = Path(__file__).resolve().parents[3] / "data" / "results"


def save_results(
    df: pd.DataFrame, stem: str, metadata: dict | None = None, results_dir: Path | None = None
) -> dict:
    """Write `<stem>.parquet`, `<stem>.csv` and `<stem>.metadata.json`.

    Returns the written paths. Parquet is the archival format because it
    preserves dtypes exactly; a boolean column round-tripped through CSV comes
    back as text, which is how analysis code silently starts comparing strings.
    """
    directory = results_dir or RESULTS_DIR
    directory.mkdir(parents=True, exist_ok=True)

    parquet_path = directory / f"{stem}.parquet"
    csv_path = directory / f"{stem}.csv"
    meta_path = directory / f"{stem}.metadata.json"

    written = {}
    try:
        df.to_parquet(parquet_path, index=False)
        written["parquet"] = parquet_path
    except Exception as exc:  # pyarrow missing or an unsupported dtype
        print(f"warning: could not write Parquet ({exc}); CSV remains authoritative")

    df.to_csv(csv_path, index=False)
    written["csv"] = csv_path

    if metadata is not None:
        meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True, default=str) + "\n")
        written["metadata"] = meta_path
    return written


def load_results(stem_or_path, results_dir: Path | None = None) -> pd.DataFrame:
    """Load results, preferring Parquet so dtypes survive."""
    path = Path(stem_or_path)
    if path.suffix in {".parquet", ".csv"}:
        return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)

    directory = results_dir or RESULTS_DIR
    parquet_path = directory / f"{path.name}.parquet"
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    csv_path = directory / f"{path.name}.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path)
    raise FileNotFoundError(f"no results found for {path.name!r} in {directory}")

"""Freeze the v2 seed manifest (data/splits/v2/seed_manifest.json).

Run once. The manifest is fully determined by exonaut.experiments.v2_protocol
(master seed, range, pool size), so anyone can rebuild it and check the
committed file; re-running refuses to overwrite.

Writing the manifest only lists seed numbers. It generates no terrain, so it
does not expose any confirmatory seed.

    python scripts/freeze_v2_seed_manifest.py
"""

from __future__ import annotations

import json
from datetime import date

from exonaut.experiments.v2_protocol import MANIFEST_PATH, build_manifest


def main() -> None:
    if MANIFEST_PATH.exists():
        print(f"{MANIFEST_PATH} exists; the v2 manifest is frozen. Refusing to overwrite.")
        return
    manifest = build_manifest()
    manifest["created"] = date.today().isoformat()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=1) + "\n")
    sizes = {k: len(v) for k, v in manifest["splits"].items()}
    print(
        f"froze v2 seed manifest -> {MANIFEST_PATH}\n  sizes {sizes}\n  checksum {manifest['checksum']}"
    )


if __name__ == "__main__":
    main()

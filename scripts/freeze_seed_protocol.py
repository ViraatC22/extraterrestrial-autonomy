"""Freeze the experimental seed protocol.

Run ONCE, before any method is tuned or any result is generated. The output,
data/splits/seed_splits.json, is committed and then treated as immutable: it
records which terrains are allowed to influence tuning and which are reserved
for the single final evaluation.

Re-running this after results exist will refuse to overwrite. That refusal is
the point - if the splits could be quietly regenerated, "held-out" would mean
nothing.

    python scripts/freeze_seed_protocol.py
"""

from __future__ import annotations

from exonaut.experiments.protocol import build_splits, splits_path, write_splits

NOTE = (
    "Frozen before the adaptive planner (ARBP) was implemented and before any "
    "method was tuned. train: RL training and prior calibration. validation: "
    "all hyperparameter/weight tuning. test: in-distribution final evaluation. "
    "ood: out-of-distribution final evaluation, never used for any tuning."
)


def main() -> None:
    path = splits_path()
    if path.exists():
        print(f"{path} already exists - the protocol is already frozen.")
        print(
            "Refusing to regenerate. Delete it deliberately only if you "
            "intend to invalidate every result produced so far."
        )
        return

    splits = build_splits(note=NOTE)
    written = write_splits(splits)
    print(f"froze seed protocol -> {written}")
    for name in ("train", "validation", "test", "ood"):
        values = splits.get(name)
        print(f"  {name:<11} n={len(values):<5} range=[{values[0]}, {values[-1]}]")
    print(f"  checksum   {splits.checksum()}")


if __name__ == "__main__":
    main()

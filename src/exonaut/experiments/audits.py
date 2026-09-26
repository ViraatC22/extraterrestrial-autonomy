"""Summary statistics for the post-hoc audits of the confirmatory run.

Shared by `scripts/audit_confirmatory.py` (which re-runs the missions and
writes the audit tables) and the API (which reads those tables), so the
numbers in the paper and the numbers in the interface come from one function.
These audits are not confirmatory analyses; see docs/RESULTS.md.
"""

from __future__ import annotations

import pandas as pd

TREATMENT = "adaptive_risk_aware_astar"
CONTROL = "risk_aware_astar"


def fault_exposure_stats(merged: pd.DataFrame, rows: pd.DataFrame) -> dict:
    """Fault-exposure summary for the "hardware faults" condition.

    `merged` holds one re-run per committed mission (columns planner, seed,
    faults_fired, term, sci, energy, termination, science_return,
    energy_spent, success); `rows` is the committed rows for that condition.
    """
    m = merged
    reproduced = float(
        (
            (m.term == m.termination)
            & ((m.sci - m.science_return).abs() < 1e-9)
            & ((m.energy - m.energy_spent).abs() < 1e-6)
        ).mean()
    )
    fired_share = m.assign(any=m.faults_fired > 0).groupby("planner")["any"].mean()
    a = m[m.planner == TREATMENT].set_index("seed")
    f = m[m.planner == CONTROL].set_index("seed")
    disc = a.success != f.success
    both = (a.faults_fired > 0) & (f.faults_fired > 0)
    none = (a.faults_fired == 0) & (f.faults_fired == 0)
    return {
        "Reproduced": reproduced,
        "FiredAdaptive": float(fired_share[TREATMENT]),
        "FiredFixed": float(fired_share[CONTROL]),
        "FiredAstar": float(fired_share["astar"]),
        "MedianSteps": float(rows.steps.median()),
        "Horizon": int(rows.max_steps.iloc[0]),
        "Discordant": int(disc.sum()),
        "DiscordantBoth": int((disc & both).sum()),
        "DiscordantNone": int((disc & none).sum()),
        "DiscordantMixed": int((disc & ~both & ~none).sum()),
    }

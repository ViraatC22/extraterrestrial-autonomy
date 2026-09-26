"""Failure case studies drawn from the committed confirmatory results.

Categories come straight from recorded outcomes. For each, one representative
mission is chosen by an explicit rule - the mission whose key measure is
closest to the category median, ties to the lowest seed - so nobody picks the
most dramatic example by hand. The representative is then re-run through the
engine (missions are deterministic) to recover detail the results table does
not hold, and the re-run is checked against its committed row before anything
from it is shown.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..environments import TRUE_CLASS_PARAMS

CATEGORIES = {
    "energy_exhausted": {
        "title": "Energy exhaustion",
        "rule": lambda d: d.termination == "energy_exhausted",
        "key": "final_distance_from_home",
        "key_label": "distance from lander when stranded (m)",
        "blurb": "The battery ran below what any move costs before the rover got home.",
    },
    "immobilized": {
        "title": "Immobilization",
        "rule": lambda d: d.termination == "immobilized",
        "key": "severe_slip_events",
        "key_label": "severe-slip events",
        "blurb": "Three consecutive severe slips: the wheels dug in and the mission ended.",
    },
    "timeout": {
        "title": "Timeout",
        "rule": lambda d: d.termination == "timeout",
        "key": "final_distance_from_home",
        "key_label": "distance from lander at the step limit (m)",
        "blurb": (
            "The step budget ran out before the mission resolved its targets. Most such "
            "rovers were parked at the lander, repeatedly asking for ground help: a livelock "
            "in the mission logic rather than a navigation failure (see the research log)."
        ),
    },
    "no_safe_objective": {
        "title": "Returned early - no safe objective",
        "rule": lambda d: d.success.astype(bool) & (d.targets_visited < d.targets_total),
        "key": "science_fraction",
        "key_label": "science fraction returned",
        "blurb": (
            "The rover got home safely, but gave up on remaining targets because no round "
            "trip fit inside the risk budget. Counted as a success in this study."
        ),
    },
}


def load_main(results_dir: Path) -> tuple[pd.DataFrame, dict]:
    frame = pd.read_csv(results_dir / "exonaut_main.csv")
    frame["science_fraction"] = frame.science_return / frame.science_possible
    meta = json.loads((results_dir / "exonaut_main.metadata.json").read_text())
    return frame, meta


def representative(rows: pd.DataFrame, key: str) -> pd.Series | None:
    if rows.empty:
        return None
    median = rows[key].median()
    ranked = rows.assign(_dist=(rows[key] - median).abs()).sort_values(["_dist", "seed"])
    return ranked.iloc[0]


def request_for(row: pd.Series, meta: dict) -> dict:
    """The MissionRequest that reproduces a committed confirmatory row."""
    cond = {c["name"]: c for c in meta["conditions"]}[row["condition"]]
    return {
        **meta["base_config"],
        "body": cond["body"],
        "prior_body": cond.get("prior_body", "moon"),
        **cond.get("overrides", {}),
        "planner": row["planner"],
        "seed": int(row["seed"]),
    }


def reproduces_row(result, row: pd.Series) -> bool:
    """Does a re-run match its committed confirmatory row exactly?"""
    return bool(
        result.termination == row["termination"]
        and abs(result.science_return - row["science_return"]) < 1e-9
        and abs(result.energy_spent - row["energy_spent"]) < 1e-6
    )


def diagnostics(session: dict, row: pd.Series) -> dict:
    """Detail recovered from the re-run, plus the check that it reproduces."""
    result = session["result"]
    reproduces = reproduces_row(result, row)
    history = result.history
    decisions = result.decisions
    pursue = [d for d in decisions if d["reason"] == "pursue_target"]
    last = pursue[-1] if pursue else None
    trip = None
    if last is not None:
        chosen = next((c for c in last["candidates"] if c.get("selected")), None)
        after = [f for f in history if f["step"] >= last["step"]]
        spent_after = history[-1]["energy_spent"] - after[0]["energy_spent"] if after else None
        if chosen is not None:
            trip = {
                "decision_step": last["step"],
                "target_id": chosen["target_id"],
                "expected_round_trip_energy": chosen.get("expected_energy"),
                "expected_energy_sd": chosen.get("energy_sd"),
                "p_failure": chosen.get("p_failure"),
                "energy_spent_after_decision": spent_after,
                # how far actual spending landed from the planner's estimate,
                # in the planner's own standard deviations
                "energy_error_in_sd": (
                    (spent_after - chosen["expected_energy"]) / chosen["energy_sd"]
                    if spent_after is not None
                    and chosen.get("expected_energy") is not None
                    and chosen.get("energy_sd")
                    else None
                ),
                "mission_ended_step": history[-1]["step"] if history else None,
            }
    body = session["request"].body
    truth = {int(k): float(v.slip_mean) for k, v in TRUE_CLASS_PARAMS[body].items()}
    final_belief = history[-1]["belief"] if history else {}
    snapshot = result.belief_snapshot
    belief_error = [
        {
            "class": int(k),
            "believed": float(final_belief[k]),
            "truth": truth[int(k)],
            "error": float(final_belief[k]) - truth[int(k)],
            "n_observations": int(snapshot[k]["n_observations"]),
        }
        for k in sorted(final_belief)
        if snapshot.get(k, {}).get("n_observations", 0) > 0
    ]
    faults = [{"step": f["step"], "fault": name} for f in history for name in f.get("faults", [])]
    return {
        "reproduces_committed_row": reproduces,
        "last_trip": trip,
        "belief_error_driven_classes": belief_error,
        "faults_fired": faults,
    }


def histogram(values: pd.Series, bins: int = 12) -> dict:
    v = values.to_numpy(float)
    if v.size == 0:
        return {"edges": [], "counts": []}
    lo, hi = float(np.min(v)), float(np.max(v))
    if hi == lo:
        hi = lo + 1.0
    counts, edges = np.histogram(v, bins=bins, range=(lo, hi))
    return {"edges": edges.round(4).tolist(), "counts": counts.tolist()}

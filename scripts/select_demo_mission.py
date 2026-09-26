"""Choose the demonstration mission by a written rule, not by eye.

The interface offers one "demo mission" for presenting. Picking the prettiest
run by hand would quietly turn a demonstration into evidence, so the choice is
made here, by a rule fixed before scanning, and the rule, every seed scanned
and why each was passed over are written out with the result.

Rule
----
Configuration: the Mission Control defaults (Mars, adaptive risk-aware A*,
56 x 56 map, 4 targets, 600 steps, risk budget 0.20, no faults, no delay,
lunar prior), on engine v1 - the engine the published results come from.

Seeds: validation seeds in ascending order (quarantine excluded), at most 40.

Select the first seed with an *adaptation event*: a target that was within
the risk budget at one target-selection decision is rejected as over budget
at the next, after the rover revised its believed mean slip for some terrain
class by at least 0.05 in between. (Slip belief feeds both risk components:
embedding risk directly, and energy risk through the 1/(1 - slip) cost term.
Both components are recorded so the demo shows which one crossed the budget.)

An earlier draft also required the terrain-risk component to rise. It was
dropped because on the chosen mission the energy component carried the
rejection; the selection is unchanged, since the chosen seed is the first one
scanned under either wording.

The mission's outcome plays no part in the choice. The demo illustrates what
an adaptation event looks like; it says nothing about how often adaptation
helps (see docs/RESULTS.md for that).

    python scripts/select_demo_mission.py
"""

from __future__ import annotations

import json
from pathlib import Path

from exonaut.experiments.protocol import load_splits
from exonaut.simulation import MissionConfig, run_mission

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "demo" / "demo_mission.json"

#: Mission Control defaults (web/src/lib/api.ts DEFAULT_MISSION)
REQUEST = {
    "body": "mars",
    "planner": "adaptive_risk_aware_astar",
    "size": 56,
    "n_targets": 4,
    "max_steps": 600,
    "risk_budget": 0.2,
    "fault_rate": 0.0,
    "comm_delay": 0,
    "terrain_uncertainty": 1.0,
    "sensor_noise_scale": 1.0,
    "sensing_radius": 6,
    "solar_rate": 2.0,
    "energy_reserve_fraction": 0.25,
    "prior_body": "moon",
    "engine": "v1",
}
BELIEF_SHIFT = 0.05
MAX_SCAN = 40

RULE = (
    "First validation seed (ascending, quarantine excluded, at most 40 scanned) on which, with "
    "the Mission Control defaults and engine v1, a target that was within the risk budget at one "
    "target-selection decision is rejected as over budget at the next, after the rover revised its "
    f"believed mean slip for some terrain class by at least {BELIEF_SHIFT} in between. The mission "
    "outcome is not part of the rule."
)


def _belief_before(history: list[dict], step: int) -> dict | None:
    """Class beliefs recorded on the last frame before a decision step."""
    earlier = [f for f in history if f["step"] < step]
    return earlier[-1]["belief"] if earlier else None


def find_event(result) -> dict | None:
    scored = [d for d in result.decisions if d["candidates"]]
    for before, after in zip(scored, scored[1:], strict=False):
        b0 = _belief_before(result.history, before["step"])
        b1 = _belief_before(result.history, after["step"])
        if b0 is None or b1 is None:
            continue
        shifts = {int(k): b1[k] - b0[k] for k in b0 if k in b1}
        klass, shift = max(shifts.items(), key=lambda kv: abs(kv[1]))
        if abs(shift) < BELIEF_SHIFT:
            continue
        was = {c["target_id"]: c for c in before["candidates"]}
        for cand in after["candidates"]:
            prior = was.get(cand["target_id"])
            if prior is None or not prior.get("within_budget") or not cand.get("reachable"):
                continue
            if cand.get("within_budget"):
                continue
            return {
                "target_id": cand["target_id"],
                "decision_before": {
                    "index": before["index"],
                    "step": before["step"],
                    "p_failure": prior["p_failure"],
                    "p_terrain": prior["p_terrain"],
                    "p_energy": prior["p_energy"],
                },
                "decision_after": {
                    "index": after["index"],
                    "step": after["step"],
                    "p_failure": cand["p_failure"],
                    "p_terrain": cand["p_terrain"],
                    "p_energy": cand["p_energy"],
                },
                "risk_budget": after["risk_budget"],
                # which component alone exceeds the budget (both can)
                "crossed_by": [
                    name
                    for name in ("terrain", "energy")
                    if cand[f"p_{name}"] > after["risk_budget"]
                ],
                "belief_class": klass,
                "belief_before": b0[klass],
                "belief_after": b1[klass],
            }
    return None


def main() -> None:
    seeds = list(load_splits().get("validation"))[:MAX_SCAN]
    config = {k: v for k, v in REQUEST.items()}
    scanned = []
    chosen = None
    for seed in seeds:
        result = run_mission(MissionConfig(**config), seed=seed, collect_history=True)
        event = find_event(result)
        scanned.append({"seed": seed, "has_event": event is not None})
        if event is not None:
            first_frame = next(
                i
                for i, f in enumerate(result.history)
                if f["decision_index"] == event["decision_after"]["index"]
            )
            chosen = {
                "seed": seed,
                "termination": result.termination,
                "event": event,
                # open a few frames before the rejection so it can be watched
                "start_frame": max(0, first_frame - 12),
                "event_frame": first_frame,
            }
            break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "label": "DEMONSTRATION CASE",
        "rule": RULE,
        "request": {**REQUEST, "seed": chosen["seed"] if chosen else None},
        "chosen": chosen,
        "scanned": scanned,
        "caveat": (
            "One mission chosen to show an adaptation event. It is not a result and does not "
            "indicate how often adaptation helps; the confirmatory study found no reliable benefit."
        ),
        "generated_by": "scripts/select_demo_mission.py",
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"chosen": chosen, "n_scanned": len(scanned)}, indent=2))


if __name__ == "__main__":
    main()

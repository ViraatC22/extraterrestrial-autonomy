"""Mission definition and the decision layer above path planning.

The mission is deliberately *not* "cover as much ground as possible". It is
the structure a real surface mission has:

    start at the lander -> visit science targets -> be back at a safe haven
    before the energy budget runs out

That structure is what makes the interesting trade-off exist. Every extra
target is science value, and also a step further from safety with less charge
in hand. An autonomy system that only maximizes science strands itself; one
that only minimizes risk returns home having done nothing. The interesting
question is where a system draws that line, and whether it redraws it when
the world turns out to be different from what it expected.

The mission manager owns the *what next* decision (which target, or give up
and go home). The planners own the *how to get there* decision.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import risk


@dataclass
class ScienceTarget:
    target_id: int
    row: int
    col: int
    value: float
    visited: bool = False
    abandoned: bool = False

    @property
    def pos(self) -> tuple[int, int]:
        return (self.row, self.col)


@dataclass
class Mission:
    home: tuple[int, int]
    targets: list[ScienceTarget]
    energy_reserve: float = 12.0  # charge to keep in hand for contingency
    risk_budget: float = 0.20  # epsilon: max tolerated P(mission failure)
    max_steps: int = 600

    @property
    def total_value(self) -> float:
        return sum(t.value for t in self.targets)

    @property
    def collected_value(self) -> float:
        return sum(t.value for t in self.targets if t.visited)

    @property
    def remaining(self) -> list[ScienceTarget]:
        return [t for t in self.targets if not t.visited and not t.abandoned]


def generate_mission(
    terrain,
    rng: np.random.Generator,
    n_targets: int = 5,
    risk_budget: float = 0.20,
    max_steps: int = 600,
    energy_reserve: float = 12.0,
) -> Mission:
    """Place a home base and science targets on traversable ground.

    Targets are spread across the map (rejection-sampled against a minimum
    separation) so a mission cannot be completed by sitting still, and so the
    route genuinely has to cross varied terrain.
    """
    size = terrain.size
    max_slope = terrain.metadata.get("max_slope_deg", 25.0)

    def _free(r, c):
        return terrain.is_traversable(int(r), int(c), max_slope)

    # home: the most open spot near the centre, so no algorithm is penalized
    # by an unlucky start
    centre = size // 2
    best, best_score = None, -1.0
    for r in range(max(0, centre - 8), min(size, centre + 8)):
        for c in range(max(0, centre - 8), min(size, centre + 8)):
            if not _free(r, c):
                continue
            r0, r1 = max(0, r - 3), min(size, r + 4)
            c0, c1 = max(0, c - 3), min(size, c + 4)
            score = 1.0 - terrain.hazard[r0:r1, c0:c1].mean()
            if score > best_score:
                best_score, best = score, (r, c)
    home = best if best is not None else (centre, centre)

    targets: list[ScienceTarget] = []
    min_separation = size * 0.18
    attempts = 0
    while len(targets) < n_targets and attempts < 4000:
        attempts += 1
        r = int(rng.integers(2, size - 2))
        c = int(rng.integers(2, size - 2))
        if not _free(r, c):
            continue
        if np.hypot(r - home[0], c - home[1]) < size * 0.15:
            continue
        if any(np.hypot(r - t.row, c - t.col) < min_separation for t in targets):
            continue
        targets.append(
            ScienceTarget(
                target_id=len(targets),
                row=r,
                col=c,
                value=float(rng.uniform(1.0, 3.0)),
            )
        )

    return Mission(
        home=home,
        targets=targets,
        risk_budget=risk_budget,
        max_steps=max_steps,
        energy_reserve=energy_reserve,
    )


class MissionManager:
    """Chooses what the robot should be doing right now.

    Policy: while there is charge to spare, pursue the remaining target with
    the best value-to-cost ratio that can be reached and returned from inside
    the risk budget. Otherwise head home. A target that cannot be reached
    within budget is abandoned rather than retried forever.
    """

    def __init__(self, mission: Mission, planner, world_model, gravity: float):
        self.mission = mission
        self.planner = planner
        self.world_model = world_model
        self.gravity = gravity
        self.returning = False
        self.current_target: ScienceTarget | None = None
        self.decision_log: list = []
        #: battery fraction at which the robot is willing to start a new sortie
        self.resume_charge_fraction = 0.80
        #: consecutive home-and-charged failures before targets are written off
        self.abandon_after = 2
        self.failed_home_assessments = 0
        #: evaluation of every candidate at the most recent decision point
        self.last_candidates: list[dict] = []

    def _round_trip_assessment(
        self,
        start,
        target_pos,
        available_energy,
        solar_efficiency: float = 1.0,
        solar_rate: float | None = None,
    ):
        """Plan out-and-back and assess whether it fits the risk budget."""
        outbound = self.planner.plan(self.world_model, start, target_pos)
        if not outbound:
            return None
        inbound = self.planner.plan(self.world_model, target_pos, self.mission.home)
        if not inbound:
            return None
        full = outbound + inbound[1:]
        assessment = risk.mission_failure_probability(
            self.world_model,
            full,
            self.gravity,
            available_energy,
            self.mission.energy_reserve,
            start=start,
            solar_efficiency=solar_efficiency,
            solar_rate=solar_rate,
        )
        assessment["outbound"] = outbound
        assessment["round_trip"] = full
        return assessment

    def select_objective(
        self,
        start,
        available_energy,
        charge_fraction: float = 1.0,
        solar_efficiency: float = 1.0,
        solar_rate: float | None = None,
    ) -> dict:
        """Return {'goal': (r,c), 'path': [...], 'returning': bool, ...}.

        Missions are flown as sorties: go out, come back, recharge, go out
        again. A target that does not fit the budget on a low battery is not
        written off - the robot returns home, recharges, and reconsiders. It
        is abandoned only once the robot is home with a recovered battery and
        still cannot reach it, which is the point at which "we cannot do this"
        is actually true rather than merely "not right now".
        """
        mission = self.mission
        candidates = mission.remaining
        at_home = start == mission.home

        if not candidates:
            path = self.planner.plan(self.world_model, start, mission.home)
            return {
                "goal": mission.home,
                "path": path,
                "returning": True,
                "target": None,
                "reason": "all_targets_resolved",
            }

        # Home with a recovered battery: start a new sortie.
        if self.returning and at_home and charge_fraction >= self.resume_charge_fraction:
            self.returning = False

        if self.returning:
            path = self.planner.plan(self.world_model, start, mission.home)
            return {
                "goal": mission.home,
                "path": path,
                "returning": True,
                "target": None,
                "reason": "return_home",
            }

        # Every candidate's evaluation is recorded, including the rejected
        # ones and why they were rejected. A planner that only reports its
        # winner cannot be audited: "it chose B" is not an explanation until
        # you can see what A scored and which constraint ruled it out.
        self.last_candidates = []
        best = None
        for target in candidates:
            assessment = self._round_trip_assessment(
                start, target.pos, available_energy, solar_efficiency, solar_rate
            )
            if assessment is None:
                self.last_candidates.append(
                    {
                        "target_id": target.target_id,
                        "row": target.row,
                        "col": target.col,
                        "science_value": target.value,
                        "reachable": False,
                        "rejected": "no believed route",
                    }
                )
                continue

            cost = max(assessment["expected_energy"], 1e-6)
            utility = target.value / cost
            over_budget = assessment["p_failure"] > mission.risk_budget
            self.last_candidates.append(
                {
                    "target_id": target.target_id,
                    "row": target.row,
                    "col": target.col,
                    "science_value": target.value,
                    "reachable": True,
                    "path_cells": len(assessment["round_trip"]),
                    "expected_energy": assessment["expected_energy"],
                    "energy_sd": assessment["energy_sd"],
                    "expected_solar_income": assessment.get("expected_solar_income", 0.0),
                    "p_failure": assessment["p_failure"],
                    "p_terrain": assessment["p_terrain"],
                    "p_energy": assessment["p_energy"],
                    "utility": utility,
                    "rejected": (
                        f"P(failure) {assessment['p_failure']:.3f} exceeds "
                        f"risk budget {mission.risk_budget:.2f}"
                        if over_budget
                        else None
                    ),
                }
            )
            if over_budget:
                continue
            if best is None or utility > best["utility"]:
                best = {"target": target, "assessment": assessment, "utility": utility}

        if best is not None:
            for entry in self.last_candidates:
                entry["selected"] = entry["target_id"] == best["target"].target_id
        else:
            for entry in self.last_candidates:
                entry["selected"] = False

        if best is None:
            self.returning = True
            # Only write targets off if we are home, charged, and still stuck:
            # otherwise this is a "not on this battery" verdict, not a "never".
            if at_home and charge_fraction >= self.resume_charge_fraction:
                self.failed_home_assessments += 1
                if self.failed_home_assessments >= self.abandon_after:
                    for target in candidates:
                        target.abandoned = True
            path = self.planner.plan(self.world_model, start, mission.home)
            return {
                "goal": mission.home,
                "path": path,
                "returning": True,
                "target": None,
                "reason": "no_target_within_budget",
            }

        self.current_target = best["target"]
        return {
            "goal": best["target"].pos,
            "path": best["assessment"]["outbound"],
            "returning": False,
            "target": best["target"],
            "reason": "pursue_target",
            "p_failure": best["assessment"]["p_failure"],
            "expected_energy": best["assessment"]["expected_energy"],
        }

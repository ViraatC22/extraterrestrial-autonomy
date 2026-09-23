"""Fixed risk-aware A* - the strong classical baseline.

Scores distance, expected energy, and believed terrain risk with fixed
weights:

    J = w_d * d + w_e * E(x) + w_r * R(x) + w_u * U(x)

where R is the believed probability that entering the cell ends the mission
and U is the epistemic uncertainty in that belief.

This planner is *risk-aware* but not *adaptive*: it consults its world model
every time it plans, but it never revises that model from driving experience.
It is therefore the control that isolates the contribution of online
adaptation - the difference between this and the adaptive planner is only
whether the model learns, because both share this same objective.

The weights are tuned on validation seeds only (see docs/PREREGISTRATION.md);
the values here are the outcome of that tuning and are frozen thereafter.
"""
from __future__ import annotations

from ..autonomy import risk
from .base import Planner

DEFAULT_WEIGHTS = {
    "distance": 1.0,
    "energy": 0.35,
    "risk": 60.0,
    "uncertainty": 8.0,
}


class RiskAwarePlanner(Planner):
    name = "risk_aware_astar"
    adaptive = False

    def __init__(self, weights: dict | None = None, **kwargs):
        super().__init__(**kwargs)
        self.weights = dict(DEFAULT_WEIGHTS if weights is None else weights)

    def step_cost(self, world_model, from_cell, to_cell, distance: float) -> float:
        w = self.weights
        row, col = to_cell
        energy = world_model.expected_energy(row, col, distance, self.gravity)
        cell_risk = risk.cell_risk(world_model, row, col)
        epistemic, _ = world_model.slip_uncertainty(row, col)
        return (w["distance"] * distance
                + w["energy"] * energy
                + w["risk"] * cell_risk
                + w["uncertainty"] * epistemic)

    def min_step_cost(self) -> float:
        # distance term alone is a valid lower bound: every other term is
        # non-negative, so the heuristic stays admissible
        return self.weights["distance"]


class AdaptiveRiskAwarePlanner(RiskAwarePlanner):
    """Risk-aware A* whose mobility model learns from driven terrain.

    This class deliberately inherits the fixed planner's objective and
    weights unchanged. The experimental treatment is therefore one switch:
    after each drive attempt, the adaptive planner incorporates the measured
    slip into the Bayesian class belief used by future plans.
    """

    name = "adaptive_risk_aware_astar"
    adaptive = True

    def observe_slip(self, world_model, record) -> None:
        world_model.ingest_slip(record)

"""Turning belief into a probability of mission failure.

Three failure modes are modeled, all computed from the robot's own belief
(never from ground truth):

1. **Embedding.** A cell is dangerous if severe slip is likely there. Under
   the belief that slip at a cell is Normal(mu, sd),

       p_severe(x) = P(slip >= SEVERE_SLIP_THRESHOLD) = 1 - Phi((thr - mu)/sd)

   Embedding requires EMBED_LIMIT consecutive severe-slip steps, so the
   per-cell embedding hazard is approximated as

       p_embed(x) = p_severe(x) ^ EMBED_LIMIT.

   This treats consecutive steps as independent, which *understates* risk in
   homogeneous terrain (severe slip is spatially correlated, so runs are more
   likely than independence implies). The approximation is stated in the
   paper rather than buried, and it is applied identically to every planner,
   so it cannot advantage one method over another.

2. **Energy exhaustion.** Expected path energy is accumulated with its
   variance; the shortfall probability is evaluated against remaining charge
   under a normal approximation.

3. **Hazard entry.** The believed probability that a cell is impassable.

Path-level risk composes the per-cell terms as independent events:

    P(fail) = 1 - prod_x (1 - p_x)

Again an approximation, again applied uniformly.
"""
from __future__ import annotations

import math

import numpy as np

from ..robot.vehicle import EMBED_LIMIT, SEVERE_SLIP_THRESHOLD


def _normal_sf(threshold: float, mean: float, sd: float) -> float:
    """P(X >= threshold) for X ~ Normal(mean, sd^2)."""
    if sd <= 1e-9:
        return 1.0 if mean >= threshold else 0.0
    z = (threshold - mean) / sd
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def severe_slip_probability(world_model, row: int, col: int) -> float:
    mean = world_model.expected_slip(row, col)
    sd = world_model.total_slip_sd(row, col)
    return _normal_sf(SEVERE_SLIP_THRESHOLD, mean, sd)


def embedding_probability(world_model, row: int, col: int) -> float:
    return float(severe_slip_probability(world_model, row, col) ** EMBED_LIMIT)


#: P(mission-ending outcome | the robot tries to enter a cell that really is
#: impassable). This is small because it is NOT the probability that the cell
#: is hazardous - it is the probability that the onboard geometric hazard
#: check *also* fails to catch it in time. Conflating the two makes every
#: long route through unsurveyed ground look near-certainly fatal, since a
#: per-cell prior hazard rate compounds over the length of the path.
HAZARD_MISSION_RISK = 0.005


def cell_risk(world_model, row: int, col: int) -> float:
    """Probability that entering this cell ends the mission.

    Embedding dominates: it is the failure mode with no recovery. A believed
    hazard mostly costs a refused command and a replan, so it enters here
    only through the small residual chance that the hazard check misses it.
    """
    p_embed = embedding_probability(world_model, row, col)
    p_hazard = float(world_model.hazard_prob[row, col]) * HAZARD_MISSION_RISK
    return float(np.clip(1.0 - (1.0 - p_embed) * (1.0 - p_hazard), 0.0, 1.0))


def risk_field(world_model) -> np.ndarray:
    """Full P(failure | enter cell) map, for visualization and for planners
    that want to precompute."""
    size = world_model.size
    out = np.zeros((size, size))
    for r in range(size):
        for c in range(size):
            out[r, c] = cell_risk(world_model, r, c)
    return out


def path_risk(world_model, path) -> float:
    """Composed probability that a path ends the mission."""
    survival = 1.0
    for (r, c) in path:
        survival *= (1.0 - cell_risk(world_model, r, c))
    return float(np.clip(1.0 - survival, 0.0, 1.0))


def path_energy(world_model, path, gravity: float,
                start: tuple[int, int] | None = None) -> tuple[float, float]:
    """(expected energy, standard deviation) for traversing a path.

    Energy variance comes from slip uncertainty propagated through the
    locomotion cost, linearized about the expected slip.
    """
    from ..robot.power import locomotion_cost

    total = 0.0
    variance = 0.0
    previous = start if start is not None else (path[0] if path else None)
    for cell in path:
        if previous is None:
            previous = cell
            continue
        distance = float(np.hypot(cell[0] - previous[0], cell[1] - previous[1]))
        if distance == 0:
            continue
        slip = world_model.expected_slip(*cell)
        sd = world_model.total_slip_sd(*cell)
        energy = locomotion_cost(distance, float(world_model.slope[cell]),
                                 world_model.believed_energy_multiplier(*cell),
                                 slip, gravity)
        total += energy
        # d/ds [1/(1-s)] = 1/(1-s)^2, so denergy/dslip = energy/(1-s)
        sensitivity = energy / max(1.0 - slip, 0.08)
        variance += (sensitivity * sd) ** 2
        previous = cell
    return float(total), float(math.sqrt(variance))


def energy_shortfall_probability(expected: float, sd: float,
                                 available: float, reserve: float = 0.0) -> float:
    """P(energy required exceeds the usable budget).

    Required energy is treated as Normal(expected, sd^2); the usable budget
    is what is in the battery minus the reserve the mission insists on
    keeping. Solar income during the traverse is deliberately NOT credited
    here, which makes this a conservative estimate.
    """
    budget = available - reserve
    return float(np.clip(_normal_sf(budget, expected, sd), 0.0, 1.0))


def expected_solar_income(world_model, path, solar_efficiency: float = 1.0,
                          solar_rate: float | None = None) -> float:
    """Energy the robot expects to harvest while driving the path.

    Ignoring this entirely makes the planner so conservative it never leaves
    home on a high-gravity body, where locomotion is expensive relative to
    battery capacity. It is estimated from *believed* illumination, so a
    robot that has not surveyed the route is relying on its prior here too.
    """
    from ..robot.power import NOMINAL_SOLAR_WH

    if not path:
        return 0.0
    rate = NOMINAL_SOLAR_WH if solar_rate is None else solar_rate
    illumination = float(np.mean([world_model.illumination[cell] for cell in path]))
    return rate * illumination * solar_efficiency * len(path)


def mission_failure_probability(world_model, path, gravity: float,
                                available_energy: float, reserve: float,
                                start: tuple[int, int] | None = None,
                                solar_efficiency: float = 1.0,
                                solar_rate: float | None = None) -> dict:
    """Total P(mission failure) for a candidate path, split by cause."""
    p_terrain = path_risk(world_model, path)
    expected, sd = path_energy(world_model, path, gravity, start=start)
    income = expected_solar_income(world_model, path, solar_efficiency, solar_rate)
    p_energy = energy_shortfall_probability(
        expected, sd, available_energy + income, reserve)
    combined = 1.0 - (1.0 - p_terrain) * (1.0 - p_energy)
    return {
        "p_failure": float(np.clip(combined, 0.0, 1.0)),
        "p_terrain": float(p_terrain),
        "p_energy": float(p_energy),
        "expected_energy": expected,
        "energy_sd": sd,
        "expected_solar_income": income,
    }

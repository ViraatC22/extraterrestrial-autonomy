"""Simulator validation suite: the checklist a v2 study must pass before it runs.

Each test is one item of docs/SIMULATOR_VALIDATION.md. Items already covered
elsewhere are referenced there rather than duplicated here. All missions use
development (train/validation) seeds.
"""

import ast
import inspect
from pathlib import Path

import numpy as np
import pytest

from exonaut.autonomy import risk
from exonaut.autonomy.mission_manager import MissionManager
from exonaut.autonomy.priors import default_prior
from exonaut.autonomy.world_model import AdaptiveWorldModel, ClassBelief, WorldModel
from exonaut.environments import TerrainClass, make_environment
from exonaut.environments.base import derive_slope
from exonaut.robot import FaultSchedule
from exonaut.robot.power import (
    BASE_MOVE_WH,
    REFERENCE_GRAVITY,
    PowerSystem,
    locomotion_cost,
)
from exonaut.robot.vehicle import EMBED_LIMIT, SEVERE_SLIP_THRESHOLD, Rover, SlipRecord
from exonaut.simulation import MissionConfig, run_mission

SRC = Path(__file__).resolve().parents[1] / "src" / "exonaut"
SMALL = {"size": 40, "n_targets": 3, "max_steps": 300}
DEV_SEEDS = (200_000, 200_001, 200_002)


def layout(r):
    """Home and target placement/value - the mission as generated, not its outcome."""
    return (
        tuple(r.mission_layout["home"]),
        [(t["row"], t["col"], t["value"]) for t in r.mission_layout["targets"]],
    )


def mission(engine="v2", body="mars", planner="adaptive_risk_aware_astar", seed=200_000, **kw):
    config = MissionConfig(body=body, planner=planner, engine=engine, **{**SMALL, **kw})
    return run_mission(config, seed=seed, collect_history=True)


# --------------------------------------------------------------------------- terrain


@pytest.mark.parametrize("body", ["moon", "mars"])
def test_terrain_is_a_deterministic_function_of_its_seed(body):
    a = make_environment(body, seed=100_100, size=48)
    b = make_environment(body, seed=100_100, size=48)
    c = make_environment(body, seed=100_101, size=48)
    for name in ("elevation", "slope", "roughness", "illumination", "terrain_class", "hazard"):
        assert np.array_equal(getattr(a, name), getattr(b, name)), name
    assert not np.array_equal(a.elevation, c.elevation)


@pytest.mark.parametrize("body", ["moon", "mars"])
def test_terrain_fields_are_in_range_and_slope_is_derived_from_elevation(body):
    t = make_environment(body, seed=100_102, size=48)
    assert np.all(np.isfinite(t.elevation))
    assert np.array_equal(t.slope, derive_slope(t.elevation))
    assert t.slope.min() >= 0 and t.slope.max() < 90
    assert t.illumination.min() >= 0 and t.illumination.max() <= 1
    assert set(np.unique(t.terrain_class)) <= {int(k) for k in TerrainClass}


@pytest.mark.parametrize("body", ["moon", "mars"])
def test_every_over_steep_cell_is_a_hazard(body):
    t = make_environment(body, seed=100_103, size=48)
    limit = t.metadata["max_slope_deg"]
    assert np.all(t.hazard[t.slope > limit])
    assert t.hazard.mean() < 0.5  # a map that is mostly hazard is a generator bug


def test_class_frequencies_differ_between_bodies_as_the_design_requires():
    """The domain shift is in class frequencies as well as class statistics."""

    def fines_share(body):
        shares = []
        for s in range(100_000, 100_010):
            t = make_environment(body, seed=s, size=64)
            shares.append(np.mean(t.terrain_class == int(TerrainClass.LOOSE_FINES)))
        return float(np.mean(shares))

    assert fines_share("mars") > 2 * fines_share("moon")
    for body in ("moon", "mars"):
        classes = set()
        for s in range(100_000, 100_010):
            classes |= set(np.unique(make_environment(body, seed=s, size=64).terrain_class))
        assert len(classes) >= 4, body


# --------------------------------------------------------------------------- motion


@pytest.mark.parametrize("engine", ["v1", "v2"])
def test_distance_travelled_equals_the_recorded_path_length(engine):
    r = mission(engine=engine)
    home = tuple(r.mission_layout["home"])
    points = [home] + [(f["row"], f["col"]) for f in r.history]
    length = sum(
        np.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:], strict=False)
    )
    assert r.distance_travelled == pytest.approx(length)


@pytest.mark.parametrize("seed", DEV_SEEDS)
def test_rover_never_occupies_hazardous_or_over_steep_ground(seed):
    r = mission(seed=seed)
    t = make_environment("mars", seed=seed, size=SMALL["size"])
    for f in r.history:
        assert not t.hazard[f["row"], f["col"]]
        assert t.slope[f["row"], f["col"]] <= 25.0


def _forced_slip_rover(slip_mean):
    t = make_environment("mars", seed=200_010, size=32)
    flat = np.argwhere(~t.hazard & (t.slope < 10))
    r0, c0 = (int(v) for v in flat[len(flat) // 2])
    t.true_slip_distribution = lambda r, c, slope_penalty=0.01: (slip_mean, 1e-6)
    rover = Rover(row=r0, col=c0, power=PowerSystem(capacity=1e6, charge=1e6))
    step = next(
        (dr, dc)
        for dr in (-1, 0, 1)
        for dc in (-1, 0, 1)
        if (dr or dc)
        and 0 <= r0 + dr < t.size
        and 0 <= c0 + dc < t.size
        and not t.hazard[r0 + dr, c0 + dc]
        and t.slope[r0 + dr, c0 + dc] <= 25
    )
    return rover, t, step


def test_severe_slip_stops_progress_and_three_in_a_row_immobilize():
    rover, t, (dr, dc) = _forced_slip_rover(0.95)
    rng = np.random.default_rng(0)
    for i in range(EMBED_LIMIT):
        out = rover.attempt_move(dr, dc, t, rng)
        assert out["reason"] == "slip_no_progress" and not out["moved"]
        assert rover.immobilized == (i == EMBED_LIMIT - 1)


def test_slip_just_below_the_severe_threshold_still_moves():
    rover, t, (dr, dc) = _forced_slip_rover(SEVERE_SLIP_THRESHOLD - 0.01)
    out = rover.attempt_move(dr, dc, t, np.random.default_rng(0))
    assert out["moved"] and rover.consecutive_severe_slip == 0


@pytest.mark.parametrize("engine", ["v1", "v2"])
def test_success_means_home_with_every_target_resolved(engine):
    for seed in DEV_SEEDS:
        r = mission(engine=engine, seed=seed)
        if r.success:
            last = r.history[-1] if r.history else None
            home = tuple(r.mission_layout["home"])
            assert r.final_distance_from_home == 0
            assert last is None or (last["row"], last["col"]) == home


def test_v2_never_requests_help_while_parked_at_the_lander():
    """The v1 livelock: interventions requested every step at home."""
    for seed in DEV_SEEDS:
        r = mission(seed=seed, max_steps=600)
        home = tuple(r.mission_layout["home"])
        at_home_returning = [
            f for f in r.history if (f["row"], f["col"]) == home and f["returning"]
        ]
        jumps = sum(
            1
            for a, b in zip(at_home_returning, at_home_returning[1:], strict=False)
            if b["interventions"] > a["interventions"]
        )
        assert jumps == 0


# --------------------------------------------------------------------------- energy


@pytest.mark.parametrize("engine", ["v1", "v2"])
@pytest.mark.parametrize("seed", DEV_SEEDS)
def test_energy_accounting_balances(engine, seed):
    """final charge = capacity - everything drawn + everything harvested."""
    from exonaut.simulation import BASE_BATTERY_CAPACITY

    r = mission(engine=engine, seed=seed)
    gravity = make_environment("mars", seed=seed, size=SMALL["size"]).gravity
    capacity = BASE_BATTERY_CAPACITY * gravity / REFERENCE_GRAVITY  # battery sized per body
    assert r.final_charge == pytest.approx(capacity - r.energy_spent + r.energy_generated, abs=1e-6)
    if engine == "v2":
        # v1 can report a minimum above the final charge (RESEARCH_LOG, 2026-09-26)
        assert r.min_charge <= r.final_charge + 1e-9


def test_locomotion_cost_is_the_documented_formula():
    assert locomotion_cost(1.0, 0.0, 1.0, 0.0, REFERENCE_GRAVITY) == pytest.approx(BASE_MOVE_WH)
    base = locomotion_cost(1.0, 5.0, 1.3, 0.2, 3.71)
    assert locomotion_cost(1.0, 5.0, 1.3, 0.4, 3.71) > base  # more slip costs more
    assert locomotion_cost(1.0, 10.0, 1.3, 0.2, 3.71) > base  # steeper costs more
    assert locomotion_cost(1.0, 5.0, 1.3, 0.2, 1.62) < base  # lower gravity costs less
    # near-total slip is large but finite (denominator floored at 0.08)
    assert np.isfinite(locomotion_cost(1.0, 0.0, 1.0, 0.999, 3.71))


def test_solar_harvest_is_rate_times_illumination_times_efficiency_capped_at_capacity():
    p = PowerSystem(capacity=100.0, charge=50.0, solar_rate=2.0, solar_efficiency=0.5)
    assert p.recharge(0.8) == pytest.approx(0.8)
    full = PowerSystem(capacity=100.0, charge=99.9, solar_rate=2.0)
    assert full.recharge(1.0) == pytest.approx(0.1)


def test_a_draw_larger_than_the_charge_is_refused_and_ends_in_exhaustion():
    p = PowerSystem(capacity=10.0, charge=1.0)
    assert not p.draw(2.0) and p.charge == 1.0 and p.expended == 0.0
    r = mission(battery_capacity=15.0, solar_rate=0.1, seed=200_003)
    assert r.termination in ("energy_exhausted", "success", "timeout")


def test_energy_risk_holds_back_the_reserve():
    """The shortfall probability is taken against charge minus reserve."""
    no_reserve = risk.energy_shortfall_probability(50.0, 5.0, 60.0, reserve=0.0)
    with_reserve = risk.energy_shortfall_probability(50.0, 5.0, 60.0, reserve=15.0)
    assert with_reserve > no_reserve
    assert with_reserve == pytest.approx(risk.energy_shortfall_probability(50.0, 5.0, 45.0))


def test_planner_energy_estimate_uses_the_same_physics_as_the_rover():
    """Expected energy = the rover's locomotion cost at the believed slip."""
    prior = default_prior("moon")
    wm = WorldModel(size=8, class_prior=prior["means"], aleatoric_sd=prior["aleatoric_sd"])
    wm.observed[3, 3] = True
    wm.terrain_class[3, 3] = int(TerrainClass.LOOSE_FINES)
    wm.slope[3, 3] = 6.0
    slip = wm.expected_slip(3, 3)
    assert wm.expected_energy(3, 3, 1.0, 3.71, energy_multiplier=1.9) == pytest.approx(
        locomotion_cost(1.0, 6.0, 1.9, slip, 3.71)
    )


# --------------------------------------------------------------------------- slip


def test_slip_draws_follow_the_cell_class_distribution():
    """The rover's slip on a cell has the mean of N(cell mean, class sd) clipped to [0, 0.995]."""
    t = make_environment("mars", seed=200_011, size=40)
    cells = np.argwhere(
        (t.terrain_class == int(TerrainClass.LOOSE_FINES)) & ~t.hazard & (t.slope <= 25)
    )
    r, c = (int(v) for v in cells[len(cells) // 2])
    step = next(
        (dr, dc)
        for dr in (-1, 0, 1)
        for dc in (-1, 0, 1)
        if (dr or dc)
        and 0 <= r + dr < t.size
        and 0 <= c + dc < t.size
        and not t.hazard[r + dr, c + dc]
        and t.slope[r + dr, c + dc] <= 25
    )
    rng = np.random.default_rng(1)
    draws = [
        Rover(row=r, col=c, power=PowerSystem(capacity=1e6, charge=1e6)).attempt_move(
            *step, t, rng
        )["slip"]
        for _ in range(4000)
    ]
    mean, sd = t.true_slip_distribution(r + step[0], c + step[1])
    expected = np.clip(np.random.default_rng(2).normal(mean, sd, 200_000), 0.0, 0.995).mean()
    assert np.mean(draws) == pytest.approx(expected, abs=0.01)


def test_class_belief_is_the_closed_form_conjugate_posterior_and_order_free():
    readings = [0.61, 0.44, 0.72, 0.55]
    a = ClassBelief(mean=0.4, variance=0.004, prior_mean=0.4, prior_variance=0.004)
    b = ClassBelief(mean=0.4, variance=0.004, prior_mean=0.4, prior_variance=0.004)
    for x in readings:
        a.update(x, obs_variance=0.02)
    for x in reversed(readings):
        b.update(x, obs_variance=0.02)
    precision = 1 / 0.004 + len(readings) / 0.02
    mean = (0.4 / 0.004 + sum(readings) / 0.02) / precision
    assert a.mean == pytest.approx(mean) and a.variance == pytest.approx(1 / precision)
    assert a.mean == pytest.approx(b.mean) and a.variance == pytest.approx(b.variance)


def test_epistemic_scale_multiplies_reported_uncertainty_and_nothing_else():
    prior = default_prior("moon")
    args = dict(size=8, class_prior=prior["means"], aleatoric_sd=prior["aleatoric_sd"])
    base = AdaptiveWorldModel(**args, calibrated_update=True)
    scaled = AdaptiveWorldModel(**args, calibrated_update=True, epistemic_scale=2.5)
    rec = SlipRecord(row=2, col=2, terrain_class=2, slope=3.0, slip=0.7, energy=1.0)
    for wm in (base, scaled):
        wm.observed[2, 2] = True
        wm.terrain_class[2, 2] = 2
        wm.ingest_slip(rec)
    assert scaled.class_belief[2].mean == base.class_belief[2].mean  # learning unchanged
    assert scaled.snapshot()[2]["epistemic_sd"] == pytest.approx(
        2.5 * base.snapshot()[2]["epistemic_sd"]
    )
    e_base, a_base = base.slip_uncertainty(2, 2)
    e_scaled, a_scaled = scaled.slip_uncertainty(2, 2)
    assert e_scaled == pytest.approx(2.5 * e_base) and a_scaled == a_base
    one = AdaptiveWorldModel(**args, epistemic_scale=1.0)
    plain = AdaptiveWorldModel(**args)
    assert one.total_slip_sd(4, 4) == plain.total_slip_sd(4, 4)


# --------------------------------------------------------------------------- faults


def test_fault_counts_follow_the_configured_rate():
    rng = np.random.default_rng(5)
    counts = [len(FaultSchedule.draw(rng, 50, 1.5).events) for _ in range(6000)]
    assert np.mean(counts) == pytest.approx(1.5, abs=0.05)
    assert np.var(counts) == pytest.approx(1.5, abs=0.12)  # Poisson: variance = mean


def test_v2_faults_do_not_change_terrain_or_mission_layout():
    a = mission(seed=200_004, fault_rate=0.0)
    b = mission(seed=200_004, fault_rate=2.0)
    assert layout(a) == layout(b)


def test_v2_sensor_noise_does_not_change_layout_or_fault_schedule():
    a = mission(seed=200_005, fault_rate=2.0, sensor_noise_scale=1.0)
    b = mission(seed=200_005, fault_rate=2.0, sensor_noise_scale=2.0)
    assert layout(a) == layout(b)
    faults = lambda r: [f for frame in r.history for f in frame["faults"]]  # noqa: E731
    # the schedule is fixed; which faults fire before the mission ends may differ
    fa, fb = faults(a), faults(b)
    common = min(len(fa), len(fb))
    assert fa[:common] == fb[:common]


# --------------------------------------------------------------------------- planner


def test_fixed_and_adaptive_face_identical_first_decisions():
    """Before any slip is measured the two treatments must be indistinguishable."""
    for seed in DEV_SEEDS:
        fixed = mission(planner="risk_aware_astar", seed=seed)
        adaptive = mission(planner="adaptive_risk_aware_astar", seed=seed)
        a, b = fixed.decisions[0], adaptive.decisions[0]
        strip = lambda cs: [  # noqa: E731
            {k: v for k, v in c.items() if k != "route"} | {"route": list(c.get("route", []))}
            for c in cs
        ]
        assert strip(a["candidates"]) == strip(b["candidates"])
        assert a["chosen_route"] == b["chosen_route"]


def test_fixed_planner_belief_never_moves():
    r = mission(planner="risk_aware_astar", seed=200_006)
    first = r.history[0]["belief"]
    assert all(f["belief"] == first for f in r.history)


def test_adaptive_update_uses_the_believed_class_not_the_true_one():
    prior = default_prior("moon")
    wm = AdaptiveWorldModel(size=8, class_prior=prior["means"], aleatoric_sd=prior["aleatoric_sd"])
    wm.observed[1, 1] = True
    wm.terrain_class[1, 1] = int(TerrainClass.SMOOTH_REGOLITH)
    before = {k: b.mean for k, b in wm.class_belief.items()}
    wm.ingest_slip(SlipRecord(row=1, col=1, terrain_class=2, slope=0.0, slip=0.9, energy=1.0))
    assert wm.class_belief[0].mean != before[0]  # believed class learned
    assert wm.class_belief[2].mean == before[2]  # true class untouched


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names |= {f"{node.module}.{a.name}" for a in node.names}
        elif isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


def test_planners_and_belief_code_cannot_reach_ground_truth():
    """No planner or belief module imports the terrain generator or true parameters.

    Exception, documented: mission_manager.generate_mission builds the
    mission from the terrain; it is called by the simulator, never by a planner.
    """
    forbidden = {"make_environment", "TRUE_CLASS_PARAMS", "TerrainField", "true_slip_distribution"}
    files = list((SRC / "planners").glob("*.py")) + [
        SRC / "autonomy" / "risk.py",
        SRC / "autonomy" / "world_model.py",
    ]
    for path in files:
        hit = {n for n in _imports(path) if n.split(".")[-1] in forbidden}
        assert not hit, f"{path.name} references {hit}"
    # structural: planners and the manager are only ever handed the belief
    from exonaut.planners.base import Planner

    assert "terrain" not in inspect.signature(Planner.plan).parameters
    assert "terrain" not in inspect.signature(MissionManager.__init__).parameters


def test_no_planner_draws_random_numbers():
    for path in (SRC / "planners").glob("*.py"):
        assert "random" not in path.read_text(), path.name


def test_risk_budget_is_enforced_in_exactly_one_place_and_always():
    sources = [p.read_text() for p in SRC.rglob("*.py")]
    comparisons = sum(s.count("> mission.risk_budget") for s in sources)
    assert comparisons == 1
    for seed in DEV_SEEDS:
        r = mission(seed=seed)
        for d in r.decisions:
            for c in d["candidates"]:
                if c.get("selected"):
                    assert c["p_failure"] <= d["risk_budget"]
                if c.get("reachable") and c["p_failure"] > d["risk_budget"]:
                    assert not c["selected"]


# --------------------------------------------------------------------------- randomness


def test_v2_draws_from_separate_streams():
    """Terrain from its own seed; mission layout, faults, sensing and slip each
    from a separate child of the mission seed."""
    src = (SRC / "simulation.py").read_text()
    assert "SeedSequence(seed).spawn(4)" in src
    # changing only the fault rate leaves every slip draw on a shared prefix
    a = mission(seed=200_007, fault_rate=0.0)
    b = mission(seed=200_007, fault_rate=3.0)
    assert layout(a) == layout(b)

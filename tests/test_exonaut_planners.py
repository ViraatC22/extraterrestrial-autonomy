from exonaut.autonomy.priors import load_prior
from exonaut.autonomy.world_model import AdaptiveWorldModel, WorldModel
from exonaut.environments import TRUE_CLASS_PARAMS
from exonaut.planners import available_planners, make_planner
from exonaut.robot.vehicle import SlipRecord
from exonaut.simulation import (
    TERMINATION_TIMEOUT,
    MissionConfig,
    build_world_model,
    run_mission,
)


def test_adaptive_planner_is_registered_and_updates_belief():
    assert "adaptive_risk_aware_astar" in available_planners()
    planner = make_planner("adaptive_risk_aware_astar")
    prior = load_prior("moon")
    model = AdaptiveWorldModel(8, prior["means"], prior["aleatoric_sd"])
    model.terrain_class[0, 0] = 2
    before = model.class_belief[2].mean
    record = SlipRecord(0, 0, terrain_class=2, slope=0.0, slip=0.9, energy=1.0)
    planner.observe_slip(model, record)
    assert model.class_belief[2].n_observations == 1
    assert model.class_belief[2].mean > before


def test_adaptation_uses_believed_class_not_simulator_truth():
    prior = load_prior("moon")
    model = AdaptiveWorldModel(8, prior["means"], prior["aleatoric_sd"])
    model.terrain_class[3, 4] = 1
    record = SlipRecord(3, 4, terrain_class=2, slope=0.0, slip=0.9, energy=1.0)
    model.ingest_slip(record)
    assert model.class_belief[1].n_observations == 1
    assert model.class_belief[2].n_observations == 0


def test_fixed_planner_does_not_update_belief():
    planner = make_planner("risk_aware_astar")
    prior = load_prior("moon")
    model = WorldModel(8, prior["means"], prior["aleatoric_sd"])
    before = model.snapshot()
    planner.observe_slip(
        model, SlipRecord(0, 0, terrain_class=2, slope=0.0, slip=0.9, energy=1.0)
    )
    assert model.snapshot() == before


def test_ood_world_model_uses_prior_body_energy_beliefs():
    config = MissionConfig(body="mars", prior_body="moon")
    model = build_world_model(config, load_prior("moon"), adaptive=False)
    expected = {
        int(k): params.energy_multiplier
        for k, params in TRUE_CLASS_PARAMS["moon"].items()
    }
    assert model.energy_multiplier == expected


def test_mission_is_deterministic_for_each_planner():
    base = dict(size=24, n_targets=2, max_steps=80)
    for planner in available_planners():
        config = MissionConfig(planner=planner, **base)
        a = run_mission(config, seed=300001).to_row()
        b = run_mission(config, seed=300001).to_row()
        assert a == b


def test_unresolved_mission_at_home_is_not_reported_as_success():
    result = run_mission(
        MissionConfig(
            planner="risk_aware_astar",
            size=20,
            n_targets=1,
            max_steps=1,
            risk_budget=0.0,
        ),
        seed=200000,
    )

    assert result.termination == TERMINATION_TIMEOUT
    assert result.success is False
    assert result.targets_visited == 0
    assert result.targets_total == 1

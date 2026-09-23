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


def test_confirmatory_seeds_never_include_quarantined():
    """The confirmatory design must not reuse terrains that were already seen
    during the engineering pilot."""
    from exonaut.experiments.protocol import load_quarantine, load_splits

    splits = load_splits()
    quarantine = load_quarantine()
    assert quarantine, "quarantine file missing: burned seeds must be recorded"
    for split_name, burned in quarantine.items():
        clean = set(splits.get(split_name))
        assert not (clean & set(burned)), (
            f"{split_name} still yields quarantined seeds {sorted(clean & set(burned))}"
        )
        # and the raw split must still contain them, proving they were removed
        # by the quarantine rather than never having existed
        raw = set(splits.get(split_name, exclude_quarantined=False))
        assert set(burned) <= raw


def _fresh_world_model(adaptive=True):
    from exonaut.autonomy.priors import default_prior
    from exonaut.autonomy.world_model import AdaptiveWorldModel, WorldModel

    prior = default_prior("moon")
    cls = AdaptiveWorldModel if adaptive else WorldModel
    return cls(size=32, class_prior=prior["means"], aleatoric_sd=prior["aleatoric_sd"])


def test_learning_generalizes_to_unobserved_terrain():
    """Adapted beliefs must change the estimate for ground the robot has NOT
    visited.

    Regression guard for a silent defect: the world model learned terrain
    slip correctly but `expected_slip` fell back to a fixed constant for any
    unobserved cell. Since planned routes are mostly unobserved cells, the
    learning never reached a single planning decision and the adaptive
    planner behaved identically to the fixed one.
    """
    from exonaut.robot.vehicle import SlipRecord

    wm = _fresh_world_model(adaptive=True)
    # pretend the robot has surveyed a patch and seen it is all class 2
    wm.terrain_class[:8, :8] = 2
    wm.observed[:8, :8] = True

    unobserved_cell = (20, 20)
    assert not wm.observed[unobserved_cell]
    before = wm.expected_slip(*unobserved_cell)

    # now drive on class-2 ground and measure much worse slip than the prior
    for _ in range(25):
        wm.ingest_slip(SlipRecord(row=1, col=1, terrain_class=2, slope=0.0,
                                  slip=0.85, energy=1.0))

    after = wm.expected_slip(*unobserved_cell)
    assert after > before + 0.05, (
        f"learning did not generalize: unobserved-cell slip estimate went "
        f"{before:.3f} -> {after:.3f}"
    )


def test_fixed_world_model_does_not_learn():
    """The control must genuinely not adapt, or the comparison is meaningless."""
    from exonaut.robot.vehicle import SlipRecord

    wm = _fresh_world_model(adaptive=False)
    wm.terrain_class[:8, :8] = 2
    wm.observed[:8, :8] = True
    before = wm.expected_slip(20, 20)
    for _ in range(25):
        wm.ingest_slip(SlipRecord(row=1, col=1, terrain_class=2, slope=0.0,
                                  slip=0.85, energy=1.0))
    assert wm.expected_slip(20, 20) == before

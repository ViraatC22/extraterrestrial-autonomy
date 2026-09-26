"""The whole-map belief views must match the per-cell functions the planner
uses, or the interface would draw a belief the robot does not hold."""

import numpy as np

from exonaut.autonomy import risk
from exonaut.autonomy.priors import default_prior
from exonaut.autonomy.world_model import AdaptiveWorldModel
from exonaut.environments import make_environment
from exonaut.robot import SensorSuite
from exonaut.robot.vehicle import SlipRecord


def _partly_observed_model():
    prior = default_prior("moon")
    wm = AdaptiveWorldModel(size=24, class_prior=prior["means"], aleatoric_sd=prior["aleatoric_sd"])
    terrain = make_environment("mars", seed=200000, size=24)
    rng = np.random.default_rng(0)
    wm.ingest_observations(SensorSuite(sensing_radius=6).observe(terrain, 8, 8, rng))
    for slip in (0.7, 0.8, 0.55):
        wm.ingest_slip(SlipRecord(row=8, col=8, terrain_class=2, slope=3.0, slip=slip, energy=1.0))
    assert wm.observed.any() and not wm.observed.all()
    return wm


def test_expected_slip_grid_matches_per_cell():
    wm = _partly_observed_model()
    grid = wm.expected_slip_grid()
    for r in range(wm.size):
        for c in range(wm.size):
            assert np.isclose(grid[r, c], wm.expected_slip(r, c))


def test_total_sd_grid_matches_per_cell():
    wm = _partly_observed_model()
    grid = wm.total_slip_sd_grid()
    for r in range(wm.size):
        for c in range(wm.size):
            assert np.isclose(grid[r, c], wm.total_slip_sd(r, c))


def test_risk_grid_matches_per_cell():
    wm = _partly_observed_model()
    grid = risk.cell_risk_grid(wm)
    for r in range(wm.size):
        for c in range(wm.size):
            assert np.isclose(grid[r, c], risk.cell_risk(wm, r, c), atol=1e-12)


def test_routable_grid_matches_the_planners_own_test():
    wm = _partly_observed_model()
    wm.hazard_prob[3, 3] = 0.9  # make sure both branches are exercised
    grid = wm.believed_traversable_grid(25.0, 0.5)
    assert grid.any() and not grid.all()
    for r in range(wm.size):
        for c in range(wm.size):
            assert bool(grid[r, c]) == wm.believed_traversable(r, c, 25.0, 0.5)


def test_true_slip_grid_matches_the_simulators_draw():
    terrain = make_environment("mars", seed=200001, size=24)
    grid = terrain.true_slip_mean_grid()
    for r in range(terrain.size):
        for c in range(terrain.size):
            assert grid[r, c] == terrain.true_slip_distribution(r, c)[0]

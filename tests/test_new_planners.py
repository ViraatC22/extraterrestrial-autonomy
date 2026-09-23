"""Correctness checks for the search-strategy baselines.

These planners exist as controls, so the properties that make them useful
controls are asserted rather than assumed: Dijkstra must find the same-cost
route as A* (isolating the heuristic), and D* Lite must return usable paths
over the same cost surface as the fixed risk-aware planner.
"""

import numpy as np
import pytest

from exonaut.autonomy.priors import default_prior
from exonaut.autonomy.world_model import WorldModel
from exonaut.environments import make_environment
from exonaut.planners import make_planner


def _world(seed=200000, size=32):
    """A world model populated from a real terrain, as a planner would see it."""
    terrain = make_environment("moon", seed=seed, size=size)
    prior = default_prior("moon")
    wm = WorldModel(size=size, class_prior=prior["means"], aleatoric_sd=prior["aleatoric_sd"])
    # reveal the map so planning is well-posed and deterministic for the test
    wm.slope[:] = terrain.slope
    wm.roughness[:] = terrain.roughness
    wm.terrain_class[:] = terrain.terrain_class
    wm.illumination[:] = terrain.illumination
    wm.hazard_prob[:] = np.where(terrain.hazard, 0.95, 0.02)
    wm.observed[:] = True
    wm._invalidate()
    return wm


def _path_cost(planner, wm, path):
    total = 0.0
    for a, b in zip(path[:-1], path[1:], strict=True):
        total += planner.step_cost(wm, a, b, float(np.hypot(b[0] - a[0], b[1] - a[1])))
    return total


def _free_endpoints(wm):
    size = wm.size
    free = [
        (r, c)
        for r in range(size)
        for c in range(size)
        if wm.believed_traversable(r, c, 25.0)
    ]
    return free[0], free[-1]


def test_dijkstra_matches_astar_cost():
    """Same cost surface, different heuristic: the route cost must agree.

    A mismatch would mean the A* heuristic is inadmissible and the 'optimal'
    paths reported elsewhere are not optimal.
    """
    wm = _world()
    start, goal = _free_endpoints(wm)
    astar = make_planner("astar", gravity=1.62)
    dijkstra = make_planner("dijkstra", gravity=1.62)

    path_a = astar.plan(wm, start, goal)
    path_d = dijkstra.plan(wm, start, goal)
    assert path_a and path_d
    assert path_a[0] == path_d[0] == start
    assert path_a[-1] == path_d[-1] == goal
    assert _path_cost(astar, wm, path_a) == pytest.approx(
        _path_cost(dijkstra, wm, path_d), rel=1e-9
    )


def test_astar_expands_no_more_than_dijkstra():
    """The heuristic should not make the search worse."""
    wm = _world()
    start, goal = _free_endpoints(wm)
    astar = make_planner("astar", gravity=1.62)
    dijkstra = make_planner("dijkstra", gravity=1.62)
    astar.plan(wm, start, goal)
    dijkstra.plan(wm, start, goal)
    assert astar.nodes_expanded <= dijkstra.nodes_expanded


def test_dstar_lite_returns_a_connected_path():
    wm = _world()
    start, goal = _free_endpoints(wm)
    planner = make_planner("dstar_lite", gravity=1.62)
    path = planner.plan(wm, start, goal)
    assert path, "D* Lite found no route on a fully revealed map"
    assert path[0] == start
    for a, b in zip(path[:-1], path[1:], strict=True):
        assert max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1, "path has a gap"


def test_dstar_lite_reuses_its_search_between_calls():
    """The point of an incremental planner is that repeating a query to the
    same goal is cheaper than the first solve."""
    wm = _world()
    start, goal = _free_endpoints(wm)
    planner = make_planner("dstar_lite", gravity=1.62)

    planner.plan(wm, start, goal)
    first = planner.nodes_expanded
    planner.nodes_expanded = 0
    planner.plan(wm, start, goal)
    second = planner.nodes_expanded

    assert first > 0
    assert second < first, f"no incremental saving: {first} then {second} expansions"


def test_all_registered_planners_are_constructible_and_plan():
    from exonaut.planners import available_planners

    wm = _world()
    start, goal = _free_endpoints(wm)
    for name in available_planners():
        planner = make_planner(name, gravity=1.62)
        path = planner.plan(wm, start, goal)
        assert path, f"{name} returned no path on a fully revealed map"
        assert path[0] == start

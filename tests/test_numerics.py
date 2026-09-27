"""Deterministic maths for engine v2: accurate, and v1 untouched."""

import math

import numpy as np
import pytest

from exonaut import numerics
from exonaut.numerics import det_erfc, det_exp, det_hypot, deterministic


def test_exp_is_within_an_ulp_or_two_of_the_library():
    for x in np.linspace(-700, 700, 20001):
        assert det_exp(x) == pytest.approx(math.exp(x), rel=5e-16)


def test_erfc_is_accurate_over_the_planners_range():
    for z in np.linspace(-6, 26, 30001):
        assert det_erfc(z) == pytest.approx(math.erfc(z), rel=1e-12, abs=1e-300)


def test_hypot_matches_the_library():
    rng = np.random.default_rng(0)
    for a, b in rng.random((5000, 2)) * 10:
        assert det_hypot(a, b) == pytest.approx(math.hypot(a, b), rel=3e-16)
    assert det_hypot(1, 1) == math.sqrt(2.0) and det_hypot(3, 4) == 5.0


def test_switch_dispatches_and_restores():
    assert not numerics.is_deterministic()
    assert numerics.erfc(0.3) == math.erfc(0.3)
    with deterministic(True):
        assert numerics.is_deterministic()
        assert numerics.erfc(0.3) == det_erfc(0.3)
        assert numerics.hypot(0.3, 0.4) == det_hypot(0.3, 0.4)
        arr = numerics.exp(np.array([0.1, -2.0]))
        assert arr[1] == det_exp(-2.0)
    assert not numerics.is_deterministic()


def test_v1_missions_never_use_the_deterministic_path(monkeypatch):
    from exonaut.simulation import MissionConfig, run_mission

    def boom(*_):
        raise AssertionError("deterministic maths used in a v1 mission")

    monkeypatch.setattr(numerics, "det_erfc", boom)
    monkeypatch.setattr(numerics, "det_hypot", boom)
    monkeypatch.setattr(numerics, "det_exp", boom)
    run_mission(MissionConfig(body="mars", size=24, n_targets=2, max_steps=60), seed=200_000)


def test_v2_missions_run_under_deterministic_maths(monkeypatch):
    from exonaut.simulation import MissionConfig, run_mission

    calls = []
    original = numerics.det_hypot
    monkeypatch.setattr(numerics, "det_hypot", lambda a, b: calls.append(1) or original(a, b))
    run_mission(
        MissionConfig(body="mars", size=24, n_targets=2, max_steps=60, engine="v2"), seed=200_000
    )
    assert calls

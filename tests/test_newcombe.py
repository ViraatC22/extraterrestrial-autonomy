"""Study 2's primary interval: Newcombe's hybrid score interval for paired proportions."""

import numpy as np
import pytest

from exonaut.experiments.analysis import newcombe_paired_ci


def pairs(n11, n12, n21, n22):
    t = [1] * n11 + [1] * n12 + [0] * n21 + [0] * n22
    c = [1] * n11 + [0] * n12 + [1] * n21 + [0] * n22
    return np.array(t, bool), np.array(c, bool)


def test_point_estimate_is_the_difference_in_success_rates():
    d, lo, hi = newcombe_paired_ci(*pairs(90, 24, 10, 106))
    assert d == pytest.approx((24 - 10) / 230)
    assert lo < d < hi


def test_no_discordance_gives_an_interval_around_zero_inside_bounds():
    d, lo, hi = newcombe_paired_ci(*pairs(100, 0, 0, 130))
    assert d == 0 and lo < 0 < hi and lo >= -1 and hi <= 1


def test_extreme_tables_stay_inside_minus_one_to_one():
    for table in ((0, 50, 0, 0), (0, 0, 50, 0), (50, 0, 0, 0), (0, 0, 0, 50)):
        d, lo, hi = newcombe_paired_ci(*pairs(*table))
        assert -1 <= lo <= d <= hi <= 1


@pytest.mark.parametrize(
    "p11,p10,p01",
    [(0.45, 0.12, 0.05), (0.40, 0.08, 0.08), (0.85, 0.05, 0.03), (0.20, 0.15, 0.05)],
)
def test_coverage_is_close_to_nominal_at_the_planned_n(p11, p10, p01):
    rng = np.random.default_rng(11)
    n, sims, truth = 230, 3000, p10 - p01
    hits = 0
    for _ in range(sims):
        counts = rng.multinomial(n, [p11, p10, p01, 1 - p11 - p10 - p01])
        _, lo, hi = newcombe_paired_ci(*pairs(*counts))
        hits += lo <= truth <= hi
    assert 0.93 <= hits / sims <= 0.975

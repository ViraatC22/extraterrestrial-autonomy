import numpy as np

from exonaut.environments.terrain_legacy import generate_terrain


def test_reproducible_with_same_seed():
    t1 = generate_terrain(size=32, seed=7)
    t2 = generate_terrain(size=32, seed=7)
    assert np.array_equal(t1.elevation, t2.elevation)
    assert np.array_equal(t1.hazard_mask, t2.hazard_mask)


def test_different_seeds_differ():
    t1 = generate_terrain(size=32, seed=1)
    t2 = generate_terrain(size=32, seed=2)
    assert not np.array_equal(t1.elevation, t2.elevation)


def test_shapes_and_dtypes():
    t = generate_terrain(size=40, seed=3)
    assert t.elevation.shape == (40, 40)
    assert t.slope.shape == (40, 40)
    assert t.hazard_mask.dtype == bool
    assert t.shadow_mask.dtype == bool


def test_is_traversable_respects_hazard_and_bounds():
    t = generate_terrain(size=20, seed=5)
    assert t.is_traversable(-1, 0, 25.0) is False
    assert t.is_traversable(0, 20, 25.0) is False
    hazard_cells = np.argwhere(t.hazard_mask)
    if len(hazard_cells) > 0:
        r, c = hazard_cells[0]
        assert t.is_traversable(int(r), int(c), 25.0) is False


def test_some_terrain_is_not_hazard():
    # a fully-hazard map would make the whole simulation unusable
    t = generate_terrain(size=48, seed=0)
    assert t.hazard_mask.mean() < 0.9

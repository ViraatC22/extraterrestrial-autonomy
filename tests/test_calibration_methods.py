"""The calibration candidates behave as documented in docs/CALIBRATION_AUDIT.md."""

import numpy as np
import pytest

from exonaut.autonomy.priors import default_prior
from exonaut.autonomy.world_model import AdaptiveWorldModel, ClassBelief
from exonaut.robot.vehicle import SlipRecord


def model(mode, **kw):
    prior = default_prior("moon")
    wm = AdaptiveWorldModel(
        size=16,
        class_prior=prior["means"],
        aleatoric_sd=prior["aleatoric_sd"],
        calibrated_update=True,
        class_assignment=mode,
        **kw,
    )
    # a map the rover has looked at: mostly smooth regolith, some fines
    wm.observed[:, :] = True
    wm.best_range[:, :] = 2.0
    wm.terrain_class[:, :] = 0
    wm.terrain_class[:, :4] = 2
    return wm


def test_weighted_update_with_unit_weights_is_the_ordinary_update():
    a = ClassBelief(mean=0.3, variance=0.004, prior_mean=0.3, prior_variance=0.004)
    b = ClassBelief(mean=0.3, variance=0.004, prior_mean=0.3, prior_variance=0.004)
    for x in (0.2, 0.45, 0.5):
        a.update(x, obs_variance=0.02)
        b.update_weighted(x, 1.0, obs_variance=0.02)
    assert a.mean == pytest.approx(b.mean) and a.variance == pytest.approx(b.variance)


def test_membership_is_a_probability_distribution():
    wm = model("responsibility")
    for reading in (None, 0.05, 0.6):
        w = wm.class_membership(5, 8, reading)
        assert w.sum() == pytest.approx(1.0) and np.all(w >= 0)


def test_a_fines_like_reading_on_a_cell_labelled_bedrock_goes_mostly_to_fines():
    """The failure the audit found: rare-class beliefs soaking up misread cells."""
    wm = model("responsibility")
    wm.terrain_class[7, 7] = 3  # one cell misread as bedrock
    w = wm.class_membership(7, 7, reading=0.6)
    assert w[2] > 0.5 and w[3] < 0.05


def test_responsibility_learning_protects_the_bedrock_belief():
    hard = model("hard")
    soft = model("responsibility")
    for wm in (hard, soft):
        wm.terrain_class[7, 7] = 3
        for _ in range(5):
            wm.ingest_slip(
                SlipRecord(row=7, col=7, terrain_class=2, slope=0.0, slip=0.6, energy=1.0)
            )
    prior_bedrock = default_prior("moon")["means"][3][0]
    assert hard.class_belief[3].mean > prior_bedrock + 0.1  # contaminated
    assert abs(soft.class_belief[3].mean - prior_bedrock) < 0.02  # protected


def test_hard_assignment_is_the_default_and_unchanged():
    prior = default_prior("moon")
    wm = AdaptiveWorldModel(size=8, class_prior=prior["means"], aleatoric_sd=prior["aleatoric_sd"])
    assert wm.class_assignment == "hard"
    with pytest.raises(ValueError):
        AdaptiveWorldModel(size=8, class_prior=prior["means"], class_assignment="magic")


def test_class_frequency_estimate_corrects_for_confusion():
    wm = model("responsibility")
    est = wm.class_frequency_estimate()
    labels = np.bincount(wm.terrain_class[wm.observed].astype(int), minlength=5) / wm.observed.sum()
    # labels over-represent rare classes by the uniform noise share c/K; the
    # estimate removes it (floored just above zero), so the common class gains
    assert est[3] <= 0.01 and est[1] <= 0.01
    assert est[0] > labels[0]
    assert est.sum() == pytest.approx(1.0)

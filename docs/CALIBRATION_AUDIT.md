# Calibration audit of the terrain-slip learner

Scope: the per-class slip belief used by both planners (the adaptive one revises it).
Data: TRAIN and VALIDATION seeds only. No v1 held-out seed and no v2 confirmatory seed
is used; `scripts/calibration_study.py` refuses any other seed and a test checks it.
The v1 learner is preserved unchanged as part of Study 1.

This document was written in two stages. Sections 1-3 (diagnosis on TRAIN seeds, the
candidate methods, and the acceptance and selection rules) were committed **before**
any candidate was run on validation seeds. Section 4 onward was added after the single
validation evaluation.

## 1. What is being calibrated

For each terrain class k the rover holds a Normal posterior over the class's mean slip,
m_k ± s_k. A nominal 95% interval m_k ± 1.96 s_k should contain the true class mean 95%
of the time. The planner also forms a per-cell predictive distribution
N(expected slip, total sd) and from it P(severe slip), which feeds P(fail).

Measured at every planning decision (the moments the belief is used), for classes with
at least one reading, clustered by mission for intervals. Train seeds 100100-100199 were
used, not 100000-100059, because those terrains calibrated the lunar prior and would
flatter it. Configuration: v2 engine, adaptive planner, confirmatory mission size, no
faults.

## 2. Diagnosis (TRAIN seeds, 100 missions per body per variant)

Raw data: `data/validation/calibration/diagnose_*.csv`. Each ablation removes one
suspected cause **using simulator truth**; ablations are diagnostic only and are not
candidate methods.

| Variant (train) | Mars 95% coverage | Moon 95% coverage |
|---|---|---|
| v2 learner as is | 0.498 [0.464, 0.534] | 0.678 [0.645, 0.709] |
| readings filed under the true class (no misclassification) | 0.736 [0.685, 0.784] | 0.977 [0.963, 0.987] |
| true dispersion instead of the lunar prior's | 0.517 | 0.636 |
| prior centred on the true class means | 0.572 | 0.635 |

Findings, by the audit's checklist:

- **Misclassification (dominant).** About 10% of slip readings are filed under the wrong
  class (9.8% Mars, 10.3% Moon). A misread label is replaced by a uniformly random class,
  so rare classes are hit hardest: on Mars true bedrock is 0.4% of the map, the rover
  drove true bedrock 13 times in 100 missions, yet its "bedrock" belief accumulated
  thousands of records, mostly from misidentified ground. Bedrock coverage was 0.10
  (Mars) and 0.28 (Moon). Filing readings under the true class alone lifts Moon coverage
  to 0.98, so with correct class assignment the Normal-Normal update itself is
  well calibrated in distribution.
- **Prior-data conflict (Mars).** With classes corrected, Mars coverage is still 0.74,
  driven by loose fines (0.43): the lunar prior puts fines slip at 0.42 with prior sd 0.063
  against a Mars truth of 0.62, three prior standard deviations away. This is the domain
  shift itself; a confident prior from the wrong world is miscalibrated by construction.
- **Dispersion misspecification (minor for the class mean).** The lunar prior's
  aleatoric spread differs from Mars (e.g. fines 0.14 vs 0.18), but replacing it with the
  truth barely changes class-mean coverage. It does affect the per-step predictive
  distribution (below).
- **Clipping / truncation (negligible).** Readings are clipped to [0, 0.995] and the
  slope-adjusted value to [0, 1]. The mean slope-adjusted reading per true class is within
  0.011 of the class mean on both bodies (`diagnose_reading_means.csv`).
- **Standard-error formula / update logic.** The conjugate update is the closed form and
  order-independent (`test_class_belief_is_the_closed_form_conjugate_posterior_and_order_free`);
  with correct classes it calibrates (Moon 0.977). Not a cause.
- **Few observations.** Coverage is worst at 3-20 readings, not at 1-2, i.e. once
  contaminated readings have pulled the belief away and shrunk its sd; small n is not the
  mechanism.
- **Independence.** Readings are independent draws given the cell; spatial correlation is
  not modelled in the simulator, so it cannot cause miscalibration here (it would matter
  on real terrain).
- **Risk estimates.** Per step, Mars severe slip (reading >= 0.80) occurred at 0.043 while
  the mean predicted P(severe) was 0.015 - under-predicted about threefold. Predictive
  90% intervals covered 0.72 of Mars readings and 0.83 of Moon readings.

## 3. Candidate methods and selection rule (fixed before validation)

Every candidate applies identically to the fixed and adaptive planners except where it
changes *learning*, which only the adaptive planner does. No candidate uses simulator
truth. Parameters are fit on TRAIN seeds only.

| Id | Method | Fitted parameters | Addresses |
|---|---|---|---|
| M1 | v2 learner unchanged | 0 | - |
| M3 | **confusion-aware assignment**: a reading is shared among classes in proportion to the probability each class produced it, from the rover's own classifier error model (nominal 12% x range factor, known from its sensor specification) and its label frequencies corrected for that error (see amendment A1) | 0 | misclassification |
| M2a | M1 + conformal scale on epistemic sd, fit on Moon train missions (prior-body data only) | 1 | overconfidence, any cause |
| M4a | M3 + conformal scale, fit on Moon train missions under M3 | 1 | both |
| M2b | M1 + conformal scale, fit on Mars train missions | 1 | both, using deployment-body development data |
| M4b | M3 + conformal scale, fit on Mars train missions under M3 | 1 | both, same caveat |

Conformal scale: s = max(1, q / 1.96), where q is the ceil((n+1) x 0.95)-th smallest
normalized residual |m - truth| / sd among the train records.

**Acceptance (VALIDATION seeds 200000-200099, one run per candidate):**

1. Mars (the confirmatory condition): 95% coverage in [0.90, 0.99], and 50%, 80%, 90%
   coverage each within 0.10 of nominal.
2. Moon: 95% coverage at least 0.90.

**Selection among accepted candidates**, in this preference order: M1, M3, M2a, M4a, M2b,
M4b - fewest fitted parameters first, then prior-body-only data before deployment-body
data. Using Mars training terrains to set an uncertainty scale is information a real
mission might not have; if a "b" candidate is selected, the paper states that.

**If no candidate is accepted**, calibration is recorded as NOT ACCEPTED, the candidate
with the smallest maximum coverage error on Mars is reported as the best available, and
the v2 freeze stays blocked for the project owner to decide.

### Amendment A1 (2026-09-26, before any validation run)

M3 as first written weighted a reading by the label error model and class frequencies
only. Reasoning through it before validation showed a flaw: every reading would leak a
fixed share of its weight into every class (about 2% into loose fines from each smooth-
ground reading, for example), biasing rare or distinctive classes towards the common
ones. A development check on 30 TRAIN seeds (100100-100129) confirmed it and tested the
standard mixture-model alternative, which also weighs how plausible the reading is under
each class's current belief:

| TRAIN, 30 seeds | Mars 95% coverage | Moon 95% coverage | Mars fines abs. error |
|---|---|---|---|
| label-only weights | 0.528 | 0.665 | 0.206 |
| responsibility weights (label x frequency x reading likelihood) | 0.703 | 0.957 | 0.099 |

**M3 (and M4a/M4b, which build on it) therefore use responsibility weights:**
w_k proportional to P(label | class k) x estimated frequency of k x N(reading; m_k,
s_k^2 + a_k^2). Label-only weighting is dropped. No validation data was used for this
amendment; it was committed before the validation run.

Reported for every candidate but **not** used for selection: class-stratified and
observation-count-stratified coverage (any class below 0.80 at the 95% level is flagged),
median interval width, per-step predictive coverage, and severe-slip reliability and
Brier score.

## 4. Validation result (added after the single evaluation run)

Full generated tables: `data/validation/calibration/RESULTS.md`. Figures:
`paper/figures/v2_calibration_curve.pdf`, `v2_calibration_by_class.pdf`. The evaluation
was run once, on validation seeds 200000-200099, after sections 1-3 and amendment A1 were
committed (commits 3e154e2, bcea137; train fit committed in 17e0d67). An earlier evaluation
process was interrupted by a session restart before it wrote any output; nothing from it
was seen.

**Verdict under the pre-specified rule: NOT ACCEPTED.** No candidate met every criterion.

| Candidate | Mars 50 / 80 / 90 / 95% | Moon 95% | Failed |
|---|---|---|---|
| M1 v2 learner | 0.25 / 0.41 / 0.49 / 0.54 | 0.65 | all Mars levels; Moon |
| M3 confusion-aware | 0.36 / 0.57 / 0.66 / 0.72 | 0.96 | all Mars levels |
| M4a (= M3; fitted scale 1.00) | same as M3 | 0.96 | all Mars levels |
| M2a scale 4.77, fit on Moon | 0.69 / 0.88 / 0.92 / **0.945** | 0.97 | Mars 50% (over-covers) |
| M2b scale 8.49, fit on Mars | 0.88 / 0.97 / 0.97 / 0.98 | 1.00 | Mars 50%, 80% |
| M4b M3 + scale 2.94, fit on Mars | 0.72 / 0.90 / 0.95 / 0.98 | 1.00 | Mars 50% |

What the result means:

1. **The misclassification defect is fixable, and fixed by M3.** With confusion-aware
   assignment the learner is calibrated in distribution at every level (Moon 0.55 / 0.83 /
   0.92 / 0.96 against 0.50 / 0.80 / 0.90 / 0.95), with no fitted parameter; its median
   error falls from 0.036 to 0.020 on Mars and from 0.029 to 0.008 on the Moon. Bedrock coverage on Mars rises from 0.27 to 0.90.
2. **What remains on Mars is the domain shift itself.** M3's Mars shortfall is concentrated
   in loose fines (95% coverage 0.27): the lunar prior is confidently wrong about the class
   the shift changes most. No method that uses only lunar information can know how wrong a
   lunar prior will be on Mars, and M4a confirms it - fit on Moon data, the extra scale is
   exactly 1.
3. **A single scale cannot calibrate every level.** The residuals are a mixture: most class
   beliefs are accurate, a few (the shifted class, and rare classes under M1) are far off.
   Stretching every interval enough to cover the far-off ones over-covers the accurate ones,
   so every scaled candidate over-covers at 50%. M2a comes closest (best available under the
   rule: maximum Mars coverage error 0.19) and reaches 0.945 at the 95% level that the tail
   risk depends on - but it does so by widening every interval about fivefold, keeps the
   misclassification bias (median error unchanged), and on the Moon predicts severe slip
   about ten times more often than it occurs (`RESULTS.md`, predictive table).
4. **Risk estimates.** Per-step severe-slip prediction on Mars moves from about a third of the
   observed rate (M1) towards it under the scaled candidates, and over-predicts on the Moon.
   M3 barely changes per-step prediction, because the planner still labels cells by its
   (sometimes wrong) class guess when predicting; only learning uses the soft assignment.

**Consequence.** The v2 freeze is blocked on this item (`V2_FREEZE_CHECKLIST.md`). Changing
the acceptance rule now, after seeing the results, is not allowed without a recorded
decision by the project owner. The options, with their costs, are in section 5.

## 5. Options for the project owner (not decided)

- **A. Freeze with M3, and state the Mars miscalibration as part of the phenomenon.** Fixes
  the one genuine defect (a learner miscalibrated even in distribution) without fitting
  anything; the remaining Mars overconfidence is what a lunar prior on Mars is, and it is the
  thing the study is about. Cost: the risk model is knowingly overconfident on Mars.
- **B. Freeze with M2a and record an explicit exception for the 50% level.** Uses prior-body
  data only; achieves 95% coverage on Mars. Cost: intervals about 5x wider for both planners,
  the misclassification bias is untouched, severe slip is over-predicted in distribution,
  and the exception is a post-hoc change to the rule, which the paper must say.
- **C. Develop a further method on train/validation data** (for example soft class
  assignment in prediction as well as learning, or a prior widened by a stated assumption
  about how different a new body may be), with a new pre-specified rule and a fresh set of
  evaluation seeds (validation seeds 200100-200199 have not been used by any calibration
  evaluation, though the power analysis ran missions on them).

Recommendation: **A**, with the Mars calibration shortfall reported as a primary limitation
and measured on the confirmatory missions as a descriptive outcome. It is the only option
that fixes a defect rather than covering it, and it keeps the planners' behaviour
interpretable. But this is the owner's decision, and it must be made and logged before the
freeze.

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

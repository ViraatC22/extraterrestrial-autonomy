# Study 2 (v2): pre-specified analysis plan

Status: **FROZEN.** Written and committed before any Study 2 confirmatory seed was used.
Authorising the run is a separate, explicit act by the project owner (section 10); this file
existing does not authorise anything. Changing anything below after the run begins would make
the study exploratory, and would have to be reported as such.

Design digest: `f3c1df55de0c` (of `experiments/configs/study2.json`)
Seed manifest checksum: `2b24c27d2710a915bf0eacccf53219648dd47dc32dd80975c9a7ccc2ccf2479e`

## 1. Question

Does online adaptation of terrain slip beliefs change safe mission completion under
terrain-model distribution shift, compared with an otherwise identical fixed risk-aware
planner, and what does it do to scientific return? No novelty is claimed.

## 2. What is compared

Two planners, identical except that the adaptive one revises its per-class slip beliefs from
measured slip (`AdaptiveWorldModel.ingest_slip`): **fixed risk-aware A\*** and **adaptive
risk-aware A\***. Distance-only A\* is run as a descriptive reference only. Shared by both:
the risk-aware objective and weights, risk budget ε = 0.20, the lunar prior (from train
terrains), energy multipliers, replanning, mission logic, engine profile **v2** (the five
Study 1 defect fixes, numerical determinism rules in `NUMERICAL_REPRODUCIBILITY.md`), and the
learner's calibration settings: **confusion-aware class assignment (M3)**, epistemic scale 1.0.

M3 was chosen by the project owner after the pre-specified calibration rule accepted no
candidate (`CALIBRATION_AUDIT.md` sections 4-6). Its known limitation - 95% interval coverage
of about 0.72 on Mars in development data, driven by the lunar prior's error on loose fines - is
stated in advance and measured descriptively (section 6).

## 3. Conditions and seeds

| Condition | Role | Body | Overrides | Seeds |
|---|---|---|---|---|
| mars | **confirmatory** | Mars, lunar prior | - | first 230 of `confirmatory_ood` |
| moon | secondary | Moon, lunar prior | - | first 230 of `confirmatory_id` |
| mars_high_uncertainty | exploratory | Mars | slip dispersion x1.5 | same 230 as mars |
| mars_faults | exploratory | Mars | fault rate 1.0 (v2: faults inside the mission) | same 230 as mars |

Seeds come from `data/splits/v2/seed_manifest.json` (master seed 20260925), disjoint from every
Study 1 split. Mission configuration: 64 x 64 map, 5 targets, 800 steps, solar harvest 2.0 Wh
per step, energy reserve 0.25. Communication delay is not a condition (no mechanism under v2;
`V2_HYPOTHESES_DRAFT.md`).

## 4. Hypotheses

- **H1 (primary).** In the Mars condition, the probability of mission success differs between
  the adaptive and fixed planners (two-sided).
- **H2 (secondary).** In the Mars condition, mean science fraction differs (two-sided).
- **H3a, H3b (secondary).** In the Moon condition, success probability (H3a) and mean science
  fraction (H3b) differ (two-sided).

No direction is hypothesised. Study 1 found an exact tie in Martian success, and development
data gave no basis for a direction.

## 5. Tests and estimates

- **H1:** McNemar exact test (two-sided binomial test on discordant pairs,
  `scipy.stats.binomtest`), α = 0.05. One primary test, so no multiplicity correction.
  Estimate: difference in success proportions, adaptive minus fixed, with Newcombe's hybrid
  score 95% interval (`analysis.newcombe_paired_ci`, coverage-tested).
- **H2, H3b:** paired t-test (two-sided) on science fraction, with a 95% t interval; Wilcoxon
  signed-rank reported alongside. **H3a:** as H1.
- **Multiplicity:** Holm correction across the secondary family {H2, H3a, H3b} at α = 0.05.
- The analysis is exactly `scripts/analyze_study2.py`, tested on a validation dry run
  (`data/validation/study2_dry_run/`).

## 6. Outcomes by tier

| Tier | Outcome |
|---|---|
| PRIMARY | Mars success difference (H1) |
| SECONDARY | Mars science fraction (H2); Moon success (H3a); Moon science fraction (H3b) |
| DESCRIPTIVE | per condition and planner: success rate, science fraction, termination mix, energy spent, severe-slip events, interventions, learner calibration (95% class-mean coverage; mean predicted vs observed severe slip per step); distance-only A\* as reference |
| EXPLORATORY | both exploratory conditions: estimates and intervals, no tests |
| POST-HOC | anything added after the data are seen, labelled as such |

## 7. Sample size

n = **230** matched seeds per condition: the smallest n (in steps of 10) giving exact power
>= 0.90 for H1 at a minimum effect of interest of 0.10, using the upper one-sided 90% bound of
the discordance rate estimated on 200 validation seeds with M3 (`POWER_ANALYSIS.md`). Fixed
before any confirmatory data; no interim looks; no optional stopping.

Verification with the final engine (after the numerical-determinism changes, same 200
validation seeds, canonical platform; `data/validation/power_analysis/final_engine_check.json`):
37 discordant pairs (24 / 13), discordance upper bound 0.223, exact power at n = 230 of
**0.888** - slightly below the 0.90 target (0.94 at the point estimate). The same sizing rule
applied to the final engine would give n = 240. The project owner decided to freeze 230 and not
move it; the achieved power is stated here so the choice is visible.

## 8. Exclusions and failures

No mission is excluded for its outcome. A software exception invalidates the whole run, which
is fixed and rerun in full, with the failure recorded in `RESEARCH_LOG.md`.

## 9. Execution, platform and output

- Run once with `python scripts/run_study2.py` on the **canonical platform** (macOS arm64,
  Python 3.13, `requirements-lock.txt`), from a clean worktree at a tagged commit. It writes
  `data/results/study2_main.csv` (columns exactly `RESULT_COLUMNS` in that script) and a
  metadata sidecar recording commit, design digest, plan hash, platform and library versions,
  and refuses to overwrite existing results.
- Then `python scripts/analyze_study2.py` writes `data/results/study2_analysis.json`.
- **Cross-platform check** (`NUMERICAL_REPRODUCIBILITY.md` section 5): the run is repeated on
  Linux x86-64; the primary conclusion is platform-robust if the H1 decision matches and the two
  primary estimates differ by no more than 0.05. Reported either way.
- Every pre-specified outcome is reported, whatever it shows.

## 10. Authorisation

The terrain generator refuses every confirmatory seed unless this file exists and
`EXONAUT_AUTHORIZE_V2_CONFIRMATORY` equals this file's SHA-256. Setting it is the owner's
decision to run Study 2; it should be done once, for the single run, and recorded in
`RESEARCH_LOG.md`.

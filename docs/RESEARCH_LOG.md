# Research Log

## 2026-09-22 - Historical baseline preserved

The original Lunar Swarm Nav project was moved under `exonaut.multiagent`. Its simulator, PPO
checkpoint, Streamlit pages, paper assets, and regression tests were retained. Package imports,
model discovery, and training output paths were updated for the new namespace. The legacy suite
passed 47 tests after migration.

## 2026-09-22 - EXONAUT protocol frozen

Created disjoint train, validation, test, and OOD seed ranges and stored their SHA-256 checksum.
Calibrated lunar and Martian slip priors from 60 training seeds per body using noisy measurements,
not ground-truth parameters.

## 2026-09-22 - Adaptive planner implemented

Added `adaptive_risk_aware_astar` as a subclass of the fixed risk-aware planner. Both treatments
share A*, objective weights, and mission logic. The adaptive planner alone forwards driven slip
records to `AdaptiveWorldModel`.

Two leakage controls were added:

1. online updates use the robot's believed terrain class, not the simulator's true class;
2. an OOD rover receives energy multipliers from its prior body, not the target body's true model.

Added deterministic and serial/parallel regression tests for the new runner.

## 2026-09-22 - Success definition corrected

The earlier implementation could label a timed-out robot at home as successful while unresolved
targets remained. Success now requires the rover to be operational, at home, and to have resolved
every target by visiting or policy-driven abandonment. A one-step regression test guards the case.

## 2026-09-22 - Pilot generated

Ran `experiments/configs/exonaut_pilot.json`: three planners, five conditions, and four matched
reserved seeds per condition (60 missions total). Regenerated the pilot after correcting the
success definition. The raw CSV and metadata sidecar are committed. Results are labeled
descriptive; the confirmatory design remains unexecuted.

## 2026-09-23 - Audit: pre-registration ordering was not achieved

An audit of file and commit timestamps shows the intended ordering was not followed:

| time (2026-09-22) | event |
|---|---|
| 21:18 | seed splits frozen |
| 22:23 | adaptive planner (ARBP) implemented and committed |
| 22:28 | pilot results generated |
| 22:32 | `docs/PREREGISTRATION.md` written |

The design called for the protocol to be frozen *before* the proposed method existed. In fact the
document was written last, after the method and after pilot results were in hand. The document's
own content is not false - it never claims to predate the planner, and it explicitly firewalls the
pilot - but it cannot be described as a pre-registration in the strict sense, and it is not
described as one anywhere in this repository. It is a confirmatory analysis plan written with
pilot-level knowledge of the system's behaviour, which is a weaker but still meaningful commitment.

This entry exists so the limitation is discoverable rather than buried. Any presentation of this
work should state it plainly if the question of pre-registration arises.

## 2026-09-23 - Eight held-out seeds quarantined

The pilot consumed test seeds 300000-300003 and OOD seeds 400000-400003. Those terrains have been
observed during development and can no longer function as held-out data. Rather than silently
shifting the confirmatory offset, they are listed in `data/splits/quarantine.json` with the
artifact that consumed them and excluded by default from `SeedSplits.get`. The confirmatory design
now draws from 496 clean seeds per split, beginning at 300004 and 400004. A regression test asserts
that no quarantined seed can reach a confirmatory run, and run metadata records the exclusion list.

## 2026-09-23 - Three defects that made the comparison uninformative

Evaluating on validation seeds (permitted for tuning) showed both bodies were degenerate: lunar
missions were dominated by timeout, and Martian mission success was identically 0.00 for all three
planners, leaving the primary outcome with no variance to analyse.

1. **Recharge dominated the horizon.** Solar income was 0.55 Wh/step against a locomotion cost of
   1-3 Wh/step, so refilling a 180 Wh battery took roughly 327 steps of a 600-step mission.
   Missions were decided by how long the robot sat still, not by its routing decisions. The harvest
   rate is now a vehicle parameter (`solar_rate`) rather than a module constant.
2. **The energy reserve did not scale with the vehicle.** `energy_reserve` was a fixed 12 Wh while
   battery capacity is scaled by gravity, giving a 6.7% margin on the Moon but only 2.9% on Mars -
   least margin exactly where the prior is most wrong. It is now
   `energy_reserve_fraction` of capacity.
3. **Locomotion cost was underestimated for every route.** `path_energy` assumed an energy
   multiplier of 1.0 for all terrain while true multipliers reach 2.4, so every planner
   systematically under-costed its routes. The world model now carries per-class believed
   multipliers, seeded from the prior body.

Defect 3 is the one that most affected interpretation: it biased all planners toward over-committing,
and it did so more severely on Mars, where the true multipliers are highest.

## 2026-09-23 - Confirmatory run executed and interpreted

750 missions on held-out seeds (test 300004-300053, OOD 400004-400053), split
checksum `c9346c400ce5`, no quarantined seed present, no run excluded.

Provenance note: the metadata sidecar records `dirty_worktree: true`, because
commits were made during the run. `git diff 063d079 a5e5081 -- src/` shows the
only change was the addition of `experiments/analysis.py`, which the sweep does
not import. Every simulation, planner, autonomy, robot, environment and runner
module was byte-identical throughout, so the results correspond to the frozen
design.

### Outcome against the stated hypotheses

- **H1 supported.** Lunar success 0.92 adaptive vs 0.90 fixed, differing on 5
  of 50 seeds, p_Holm = 1.000. Adaptation costs nothing when the prior is right.
- **H2 not supported.** Martian science fraction moved *against* the
  hypothesis, -0.015, p_Holm = 1.000, and Martian success was exactly tied
  (5 discordant seeds each way). The validation-set advantage of +0.125 to
  +0.167 that motivated H2 did not replicate on held-out seeds.
- **H3 partially supported.** Mission success under injected faults rose from
  0.26 to 0.46 (+0.200, p_Holm = 0.020), the only contrast surviving Holm
  correction across the ten-member primary family. The discordant pairs are
  one-sided: adaptation won all 10 of them. The other degraded conditions move
  the same direction without reaching corrected significance.
- **H4** is descriptive only in this run and is reported in the tables.

### The finding we did not predict

Distance-only A* achieved the *highest* Martian success rate in three of four
conditions (0.48 vs 0.34 / 0.34 in the baseline OOD condition) while returning
the least science (0.101 vs 0.173 / 0.158). Ground interventions per mission
were 57.5 for distance-only against 102.8 for fixed risk-aware. The reading
supported by those counts is that risk-averse routing is expensive when nearly
all ground is hazardous: detours cost distance and time, and exposure is paid
per metre travelled. The current objective treats caution as free, which is a
real limitation of the formulation rather than an incidental result.

### Methodological value of the frozen protocol

The validation-to-confirmatory divergence is the clearest argument in this
project for having frozen the splits. A +0.125 to +0.167 tuning-set effect
became 0.000 on held-out data. Without the split, that first figure is the one
that would have been reported.

## 2026-09-25 - Defect: the adaptive learner is ~7x overconfident

Found while preparing a truth-vs-belief visualization. A screenshot showed the
rover believing Martian loose-fines slip was 0.776 against a true 0.620. That
belief rested on only three slip readings.

The Normal-Normal update in `autonomy/world_model.py` uses
`SLIP_OBS_VARIANCE = 0.02**2` as the noise on each reading. That treats a slip
reading as a precise measurement of the class *mean*. It is not: individual
readings scatter around the mean by the terrain's own dispersion (0.04-0.18 sd
depending on class). With the variance understated ~50x, a single reading moves
the belief ~90% of the way to that reading, and the reported uncertainty is far
too small.

Measured on 40 Martian validation missions (173 class beliefs):

| | 95% interval coverage | median abs. error | median reported sd |
|---|---|---|---|
| current rule | **0.20** | 0.060 | 0.0089 |
| per-reading variance = class aleatoric + sensor | 0.85 | 0.017 | 0.0250 |

(A calibrated model would give coverage 0.95.) The residual shortfall under the
corrected rule is expected: the rover takes its aleatoric spread from the lunar
prior (0.14 for fines) while Martian fines disperse at 0.18.

**Consequence for the confirmatory result.** The 750-mission run evaluated the
adaptive planner *with this overconfident rule*. That result is not invalid - it
is an honest test of the method as specified - but it tests a learner that
over-reacts to single readings, which may explain part of why adaptation did not
improve science return. The earlier README guess that the overshoot came from
"selection bias from retried cells" was wrong and has been corrected.

**Not yet changed.** Altering the rule and re-evaluating on the same held-out
seeds would be post-hoc tuning. Open decision: evaluate a corrected learner as a
separately declared study on held-out seeds not yet used (test 300054+,
OOD 400054+), with the plan frozen before it runs.

## 2026-09-25 - Shared random stream couples fault draws to slip draws

`run_mission` draws terrain, mission layout, the fault schedule and every wheel
slip from one `numpy` Generator in sequence. Two consequences, found while
checking why a small Scenario Lab sweep looked flat:

1. With `fault_rate` 0.5 and 1.0 the Poisson fault count often coincides, and
   the fault details are then drawn from the same stream state, so the two
   missions are byte-identical. This is a common-random-numbers effect, not a
   wiring bug.
2. With `fault_rate` 0 the fault draw is skipped, so every later slip draw is
   shifted. A "faults vs no faults" comparison therefore also changes the entire
   slip-noise realisation.

The primary confirmatory contrasts are unaffected: they compare planners within
one condition, and both members of a pair share one stream. Cross-condition
comparisons are valid in expectation but noisier than necessary. The fix -
independent streams per purpose via `numpy.random.SeedSequence.spawn` - changes
every mission outcome, so it would break reproduction of the committed results.
Deferred to any v2 study, to be declared before that study runs.

## 2026-09-25 - Defect: ground-intervention relaxation never resets

The mission loop's comment says that on an intervention "ground relaxes the
hazard threshold for one planning cycle". The code adds 0.15 to
`planner.hazard_threshold` and never restores it, so it ratchets:
0.50 -> 0.65 -> 0.80 -> 0.95 after three interventions, and stays there.
Verified on validation seed 200000 (Mars, adaptive): 15 interventions, threshold
at 0.95 for the remainder of the mission.

At 0.95 the planner treats a cell it believes 94% likely to be impassable as
routable. Martian confirmatory missions averaged 57-103 interventions, so in most
of them the planners' hazard avoidance was effectively disabled early; only the
rover's onboard geometric check (which refuses true hazards) prevented worse
outcomes.

Applied identically to every planner, so it does not favour one method within a
paired contrast. It does change what the Martian results describe, and it is a
plausible contributor to the very high intervention counts and to distance-only
A* surviving as well as it did. Recorded here; not changed, for the same reason
as the calibration defect above.

# Engine v2: validation status and a draft confirmatory plan

> **Superseded on 2026-09-26** by `V2_HYPOTHESES_DRAFT.md` (question, hypotheses, outcomes),
> `CALIBRATION_AUDIT.md` (learner calibration), `POWER_ANALYSIS.md` (sample size),
> `SIMULATOR_VALIDATION.md` (pre-freeze checks) and `V2_FREEZE_CHECKLIST.md` (the gate).
> Two things below are out of date: v2 now uses fresh confirmatory seeds from
> `data/splits/v2/seed_manifest.json`, not the unused v1 held-out seeds (section 4), and comm
> delay is removed from the confirmatory design. Kept as the record of the earlier draft.

Status: **DRAFT. Not frozen. No v2 confirmatory run has been made or scheduled.**
Sections 3 and 4 hold decisions that belong to the project owner. Nothing in this
file may be treated as pre-specified until section 5's freeze has happened and
been committed.

## 1. Why this exists

The v1 confirmatory study was run on an engine later found to have five defects
(`RESEARCH_LOG.md`). v2 fixes them behind `MissionConfig.engine = "v2"`; v1 still
reproduces all 750 committed missions. A new confirmatory study on v2 is only
worth running if, before it runs, (a) each fix is shown to do what it claims,
(b) the design is changed wherever v2 makes a v1 condition meaningless, and (c)
the design, engine and seeds are frozen, with seeds nobody has looked at.

## 2. What is already validated

Each fix has a regression test and a behavioural check on validation seeds only
(`EXPLORATION_V2.md`, generated from 1,200 validation missions).

| Defect in v1 | v2 fix | Unit evidence | Behavioural evidence (validation) |
|---|---|---|---|
| Learner overconfident: per-reading variance ignored class spread | calibrated update | `test_v2_calibrated_update_moves_less_on_one_reading` | `EXPLORATION_V2.md` §1: coverage improves but stays far below 0.95 |
| Faults scheduled across the whole horizon, most after the mission ended | faults drawn inside a 50-step window | `test_v2_faults_are_scheduled_inside_the_window` | §1: share of fault-condition missions where a fault fired |
| One random stream: changing fault rate shifted every later draw | four independent streams | `test_v2_streams_isolate_faults_from_slip_draws` | by construction |
| Intervention relaxation ratcheted the hazard threshold up to 0.95 | relaxation lasts one planning cycle | `test_v2_intervention_relaxation_lasts_one_cycle` | §1: help requests per mission |
| Rover parked at the lander asked for help every step (livelock) | recharge and reconsider instead | `test_v2_removes_the_lander_livelock` | §1: help requests in lander timeouts |
| (compatibility) v1 must be unchanged | profile switch, default v1 | `test_default_engine_is_v1_and_reproduces_committed_rows`; `scripts/verify_v1_reproduction.py` | 750/750 committed missions reproduce |

## 3. Open problems before a design can be frozen (owner decisions)

1. **The comm-delay condition is degenerate under v2.** Delay only costs time
   when the rover asks for help, and v2 almost never asks, so those missions are
   identical to plain Mars OOD (`EXPLORATION_V2.md` §2). Options: drop the
   condition; redefine delay so it binds (for example, a fixed uplink wait before
   each new objective); or keep it and pre-state it as a null control. Any
   redefinition must be explored on validation seeds before freezing.
2. **The learner is still miscalibrated.** v2 raises 95% coverage but not to
   anywhere near 0.95; the rest comes from terrain misclassification (about 12%
   of readings go to the wrong class). Options: accept and state it; or change
   the update (for example, discount readings by class confidence) and explore
   that on validation first. Changing it changes the method under test.
3. **Sample size.** `EXPLORATION_V2.md` §4 estimates the matched seeds needed
   per condition for a ±0.05 interval on the success difference, from the v2
   spread on validation. Those estimates, not the v1 figure of 50, should set n.
   Both held-out splits have enough unused seeds (§4 there).
4. **Hypotheses.** H1-H4 were written for v1. The v2 study should state its own,
   before seeing any v2 held-out data. The exploration suggests the honest
   primary question is whether any survival difference remains once the engine
   is fixed, not whether adaptation helps by a large margin.

## 4. Seeds

- Candidate ranges: `test` from 300054 and `ood` from 400054 upward, in split
  order, skipping quarantined seeds. The v1 run used 300004-300053 and
  400004-400053; those are spent for confirmatory purposes.
- **Untouched means untouched.** Since 2026-09-25 the API appends every request
  that exposes an unused held-out seed to `data/splits/heldout_access_log.jsonl`
  (`service.record_heldout_access`). Before freezing, the chosen range must be
  checked against that log. Before that date there is no log; the scripts that
  ran missions before then used validation seeds or the v1 confirmatory seeds
  only (`explore_v2.py`, `audit_confirmatory.py`, `select_demo_mission.py`, the
  sweep and failure endpoints), which can be checked in git history, but
  interactive use of the interface was not recorded.

## 5. Freeze procedure (when the decisions above are made)

1. Resolve section 3 on validation seeds only, logging each change in
   `RESEARCH_LOG.md`.
2. Write the v2 analysis plan (a new file, modelled on `PREREGISTRATION.md`):
   hypotheses, conditions, planners, n, seed range, outcomes, tests, Holm
   families, exclusions, stopping rule. Keep the v1 analysis code unchanged
   unless the plan says otherwise.
3. Check the seed range against `heldout_access_log.jsonl`; record the check.
4. Commit the plan and tag the commit. The run's metadata must record that
   commit and the engine configuration digest.
5. Run once. Report every pre-stated outcome, whatever it shows. The v1 results
   stay in the paper as they are; v2 is reported as a second, separately
   pre-specified study, not a replacement.

# Study 2 (v2): research question, hypotheses and outcomes — DRAFT

Status: **draft for the project owner. Not frozen.** Nothing here is pre-specified
until `docs/PREREGISTRATION_V2.md` exists and every item of
`docs/V2_FREEZE_CHECKLIST.md` is checked. No v2 confirmatory seed has been used.

## Research question

> Does online adaptation of terrain traction (slip) beliefs improve safe mission
> completion under terrain-model distribution shift, compared with an otherwise
> identical fixed risk-aware planner, and what trade-off does adaptation impose on
> scientific return?

No novelty is claimed. Online terrain-property learning for rover mobility is an
established research topic (see `docs/REFERENCES.md`); this study is a controlled,
pre-specified test of one simple form of it inside this simulator.

## Why Study 2 is narrower than Study 1

Study 1 tested four hypotheses across five conditions. Two of its conditions turned
out not to mean what their names said (faults rarely fired; comm delay acted only
through help requests, which v1 generated mostly in a livelock at the lander), and the one significant contrast was not the effect it was
labelled as. Study 2 therefore asks one confirmatory question in one condition,
with everything else secondary or descriptive.

## Treatments

| | Fixed risk-aware A* | Adaptive risk-aware A* |
|---|---|---|
| Objective, costs, risk model, risk budget ε | identical | identical |
| Prior (lunar, from train terrains), energy multipliers | identical | identical |
| Calibration scale on epistemic uncertainty | identical (same value) | identical (same value) |
| Replan cadence, mission logic, engine (v2) | identical | identical |
| Revises class slip beliefs from measured slip | **no** | **yes** |

The only code difference is `AdaptiveWorldModel.ingest_slip`. Tests pin this
(`test_fixed_and_adaptive_face_identical_first_decisions`,
`test_fixed_planner_belief_never_moves`). Distance-only A* is run as a descriptive
reference; no hypothesis concerns it.

## Conditions

| Condition | Role | Why |
|---|---|---|
| **Mars, lunar prior** (terrain-model shift) | **confirmatory** | the question is about distribution shift |
| Moon, lunar prior (in-distribution) | secondary | checks adaptation does not harm familiar-domain behaviour |
| Mars + 1.5× slip dispersion | exploratory | a second shift severity; not powered |
| Mars + faults (v2: faults inside the mission) | exploratory | fault handling is not what adaptation targets |
| ~~Mars + comm delay~~ | **removed** | see below |

### Why comm delay is removed

In this model a communication delay has exactly one mechanism: after the rover asks
mission control for help, it waits `comm_delay` steps. Under v2 the rover almost never
asks (`EXPLORATION_V2.md` §1: median 0 requests per Mars mission), so the condition
produced missions identical to plain Mars (`EXPLORATION_V2.md` §2). A condition whose
treatment never acts cannot support any inference about latency.

To mean something, delay would need a modelled mechanism the single rover actually
depends on - for example ground-approved tasking of each new objective, delayed map
or belief uplinks, or intervention latency during recoveries that v2 still performs.
None of these exists in the model, and inventing one only to keep the condition would
be adding a mechanism to produce an effect. The variable stays available in the
Scenario Lab as an exploratory control, labelled as having no mechanism under v2.

## Outcomes and tiers

| Tier | Outcome | Condition(s) |
|---|---|---|
| **PRIMARY** | mission success (returned safely with every target resolved) | Mars |
| SECONDARY | science fraction returned | Mars |
| SECONDARY | mission success; science fraction | Moon |
| DESCRIPTIVE | energy spent; termination mix (immobilized, energy exhausted, timeout); severe-slip events; interventions; early returns; route length | all |
| DESCRIPTIVE | learner calibration on the confirmatory missions (interval coverage, severe-slip Brier score) | all |
| EXPLORATORY | everything in the exploratory conditions; any mechanism analysis | - |
| POST-HOC | anything added after the confirmatory data are seen, labelled as such | - |

## Hypotheses

**H1 (primary, two-sided).** In the Mars condition, the probability of mission
success under the adaptive planner differs from that under the fixed planner, on
matched seeds.

*Why two-sided.* A directional hypothesis would need a basis. Study 1 found an exact
tie on Mars success (0.34 vs 0.34, 50 seeds) and the v2 validation exploration found
differences of 0.00 to +0.10 with intervals touching zero. Neither justifies a
direction, so none is claimed.

**H2 (secondary, two-sided).** In the Mars condition, mean science fraction differs
between the planners on matched seeds.

*Why not non-inferiority.* A non-inferiority test needs a margin fixed in advance and
justified by what science loss would be acceptable. This project has no external
basis for such a margin (science value is an abstract score), and choosing one after
seeing Study 1 would risk choosing it to pass. H2 is therefore a two-sided test; its
confidence interval is reported and interpreted as an estimate of the trade-off.

**H3 (secondary).** In the Moon condition, success and science fraction do not differ
between planners (two-sided tests; a significant difference in either direction is
reported as such).

**Mechanism (descriptive only).** If H1 shows a difference, the report describes how
the termination mix differs (for example fewer immobilizations or fewer energy
exhaustions) and whether the adaptive learner's belief error on the classes driven is
smaller. This is not a mediation analysis and makes no causal claim about mechanism.

## Tests and estimates (to be frozen)

- H1: McNemar exact test, two-sided, α = 0.05, on discordant seed pairs. There is one
  primary test, so no multiplicity correction applies to it. Estimate: difference in
  success proportions with a 95% interval (method to be fixed in the plan; the v1 code
  uses a t interval on paired differences - a score-based paired interval such as
  Newcombe's is preferable and would need implementing and testing before freeze).
- H2, H3: paired t-test for science fraction (Wilcoxon companion reported); McNemar
  exact for Moon success. Holm correction across the secondary family (three tests).
- All pre-specified outcomes are reported whatever they show. No exclusions; a software
  exception invalidates the whole run, which is fixed and rerun in full.
- Fixed n from `POWER_ANALYSIS.md`; no interim looks, no optional stopping.

## Owner decisions still open

1. Calibration: no candidate met the pre-specified rule (`CALIBRATION_AUDIT.md` §4). Choose
   option A (freeze with the confusion-aware learner M3, Mars shortfall reported), B (Moon-fit
   scale M2a with a logged exception) or C (develop further on development seeds).
2. Confirm the minimum effect of interest used for the sample size (`POWER_ANALYSIS.md`).
3. Confirm H1 two-sided and H2 two-sided (rather than directional / non-inferiority).
4. Confirm that faults and higher dispersion stay exploratory.

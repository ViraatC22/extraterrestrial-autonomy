# EXONAUT Confirmatory Analysis Plan

Status: **frozen design; confirmatory run not yet executed or interpreted.**

## What this document is, and is not

This is a confirmatory analysis plan. It is **not** a pre-registration in the strict sense, and
should not be described as one. The intended ordering - freeze the protocol before the proposed
method exists - was not achieved. The actual ordering, from commit and file timestamps, was:
seed splits frozen 21:18, adaptive planner committed 22:23, pilot results generated 22:28, this
document written 22:32, all on 2026-09-22. See `RESEARCH_LOG.md` for the full entry.

So this plan was written by authors who had already seen an engineering pilot on eight seeds. That
is weaker than a true pre-registration and is disclosed here rather than left for a reader to
discover. What it still provides is a commitment, fixed in version control before the confirmatory
run, to specific hypotheses, outcome measures, contrasts, and a multiplicity correction - made
before any confirmatory data existed.

The eight seeds consumed by that pilot are permanently quarantined
(`data/splits/quarantine.json`) and cannot appear in any confirmatory result.

## Hypotheses

- **H1:** On lunar in-distribution terrain, fixed and adaptive risk-aware A* will have equal or
  similar mean science fraction; adaptation should not materially harm familiar-domain behavior.
- **H2:** On Martian out-of-distribution terrain with a lunar prior, adaptive risk-aware A* will
  yield higher paired science fraction than fixed risk-aware A*.
- **H3:** Under increased slip dispersion and injected rover faults, adaptive risk-aware A* will
  have a higher mission-success rate and fewer severe-slip events than fixed risk-aware A*.
- **H4:** Ground-intervention delay will reduce mission productivity for all planners; planners
  requiring more interventions will incur a larger loss.

## Frozen design

- Configuration: `experiments/configs/exonaut_main.json`
- Planners: distance-only A*, fixed risk-aware A*, adaptive risk-aware A*
- Conditions: lunar ID, Martian OOD, Martian high uncertainty, Martian faults, Martian communication
  delay
- Seeds: first 50 seeds from the condition's reserved `test` or `ood` split, **after** removing
  quarantined seeds. Confirmatory test seeds therefore begin at 300004 and OOD seeds at 400004.
- Terrain: 64 x 64 cells
- Science targets: 5
- Horizon: 600 steps
- Prior body: Moon in every condition
- Solar harvest: 2.0 Wh/step at full illumination
- Energy reserve: 0.25 of battery capacity (a fraction, so it scales with the gravity-scaled
  battery rather than shrinking to 2.9% on Mars)

These last two values, and the per-class believed energy multipliers, were set on **validation**
seeds after the defects recorded in `RESEARCH_LOG.md` were found. No test or OOD seed informed
them.

The `test` and `ood` splits may not be used to change planner weights, risk thresholds, mission
logic, or outcome definitions. Tuning must use `validation` seeds and be recorded before rerunning
the confirmatory design.

## Primary outcomes and contrasts

1. Science fraction, adaptive versus fixed risk-aware A*, paired within condition and seed.
2. Mission success, adaptive versus fixed risk-aware A*, paired within condition and seed.

Distance-only A* is a control. Secondary comparisons involving it are labeled secondary.

## Multiplicity and reporting

Continuous paired contrasts use two-sided paired t-tests with Wilcoxon companions, 95% confidence
intervals, Cohen's paired effect size, and Holm adjustment across the prespecified family. Report
all outcomes regardless of significance. Binary success should use an exact matched-pairs test or a
mixed-effects logistic model with seed as a block.

## Pilot firewall

`exonaut_pilot.csv` is an engineering pilot with four seeds per condition. It may expose software
defects and runtime feasibility but may not justify post-hoc changes intended to improve a planner's
ranking. Any necessary defect correction must be documented in `RESEARCH_LOG.md`, regression-tested,
and followed by regeneration of the pilot. Pilot p-values are not confirmatory evidence.

## Stopping and exclusions

No successful or failed trial is excluded. A software exception invalidates the affected run and
must be fixed before the complete sweep is regenerated. The confirmatory run stops after the fixed
number of seeds; no optional stopping is allowed.

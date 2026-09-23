# Methodology

The paper in `paper/paper.tex` is the authoritative narrative. This document is the compact,
implementation-facing specification.

## Research question

When a planetary rover enters terrain whose mobility statistics differ from those used to
calibrate its prior, does updating the onboard slip model from proprioceptive experience improve
science return and mission completion compared with fixed risk-aware and distance-only planning?

## Treatments

All planners share the same eight-connected A* implementation.

- `astar` minimizes geometric distance.
- `risk_aware_astar` uses fixed distance, expected-energy, terrain-risk, and epistemic-uncertainty
  costs.
- `adaptive_risk_aware_astar` uses the identical cost function and weights but updates its
  per-class slip posterior after each drive attempt.

The fixed/adaptive comparison therefore isolates online belief updating rather than search quality
or objective tuning.

## World and belief separation

`TerrainField` is simulator ground truth. A planner never receives it. The rover instead builds a
`WorldModel` from range-dependent noisy slope, roughness, illumination, hazard, and terrain-class
observations. Slip is observed proprioceptively only after a drive attempt.

The adaptive update is Normal-Normal conjugate inference over the mean slip for the terrain class
the rover *believes* occupies the driven cell. It deliberately does not use the simulator's true
class label. Posterior variance represents epistemic uncertainty; class dispersion represents
aleatoric uncertainty.

## Mission

Each mission starts at a safe home cell, places separated science targets on traversable terrain,
and requires the rover to decide between pursuing another target and returning home. A mission is
successful only if the rover is operational, is home, and has resolved every target by visiting or
abandoning it under the mission policy.

The mission manager ranks reachable targets by science value divided by expected energy, subject
to a risk budget for the planned round trip. When no route is acceptable, the rover requests ground
help and waits for the configured communication delay.

## Failure model

Mission-ending or mission-degrading mechanisms include:

- repeated severe slip causing permanent embedding;
- energy exhaustion;
- geometric hazard refusal followed by replanning;
- sensor degradation;
- lower motor efficiency;
- reduced solar efficiency; and
- wheel damage that increases slip.

Fault schedules are drawn completely from the trial seed before a mission starts, so every planner
faces the same fault timing and severity within a matched block.

## Environments and domain shift

The Moon and Mars share a five-class terrain vocabulary but have different class distributions and
class parameters. The lunar environment includes craters and permanent shadow. The Martian
environment includes directional drift bands, different slip ordering, diffuse illumination, and
higher gravity.

All planners use priors calibrated from noisy measurements on lunar `train` seeds. In Martian OOD
conditions they retain lunar slip and energy beliefs at mission start. Passing true Martian class
parameters into the planner would be leakage and is covered by regression tests.

## Outcomes

Primary outcomes:

- science fraction: collected science value divided by possible value;
- mission success: safe return with all targets resolved.

Secondary outcomes:

- targets visited;
- energy spent and generated;
- minimum and final charge;
- severe-slip events and immobilization;
- human interventions and communication waiting;
- replans and A* nodes expanded.

## Statistical design

Every planner receives the same `(condition, seed)` world, targets, stochastic draws, and fault
schedule. The seed is the experimental block. Primary planner contrasts must therefore be paired.

The 60-mission pilot uses four seeds per condition and is descriptive. The confirmatory design uses
50 seeds per condition. Pairwise tests use paired differences with Holm correction and report
effect sizes and confidence intervals. Binary mission success is summarized with matched counts;
the confirmatory analysis should use a paired binary model or exact matched test rather than an
ordinary independent-proportions test.

## Reproducibility controls

- `data/splits/seed_splits.json` is immutable and checksummed.
- train, validation, test, and OOD ranges are disjoint.
- priors record their calibration seeds.
- every result CSV has a JSON design/checksum sidecar.
- serial and multiprocessing sweeps are regression-tested for equality.
- paper tables and figures are generated from row-level CSVs.

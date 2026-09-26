# Architecture

## Primary execution path

```text
MissionConfig + frozen seed
          |
          v
Moon/Mars TerrainField (simulator truth)
          |
          v
Rover sensors -----> WorldModel belief
                         |
                         v
MissionManager <---- Planner registry
      |                  |
      +---- objective ---+
                         |
                         v
                    shared A* search
                         |
                         v
Rover attempt_move -> power/slip/fault outcome
          |                    |
          +--- slip record ----+
                         |
             adaptive update only
```

`run_mission()` owns ground truth and stochastic execution. Planners receive only `WorldModel`.
`MissionManager` chooses what to do; planners choose how to reach it; `Rover` enforces motion,
energy, and local safety mechanics.

## Package boundaries

- `environments`: deterministic world generation and shared terrain vocabulary.
- `robot`: physical state transition and observation channel.
- `autonomy`: belief, uncertainty, path-risk composition, and mission-level decisions.
- `planners`: one search implementation with treatment-specific edge costs and update hooks.
- `experiments`: immutable data partitioning, batch execution, provenance, and inference.
- `multiagent`: retained historical swarm project; it does not participate in EXONAUT trials.

## Information-flow rule

Simulator truth may be read only by the world generator, noisy sensor channel, and rover physics.
Autonomy code receives beliefs and proprioceptive records. The local hazard refusal in `Rover` is
modeled as an independent near-field safety layer, not foresight by the global planner.

## Determinism

One integer seed determines terrain, target placement, sensor noise, faults, and slip draws.
Planner comparisons are valid only when condition and seed match. Batch row order is sorted after
parallel execution so a result is stable across worker counts.

## Interface data path

The mission-control interface (`web/`) is a client of the FastAPI service in
`src/exonaut/api/`, which runs missions through the same `run_mission` the
experiments use and serves recorded state. The frontend formats and draws; it
does not derive displayed quantities. The rule, and the engine function behind
every displayed number, are in `DATA_FLOW.md`.

| Endpoint | Serves |
|---|---|
| `POST /start-mission` | runs a mission to completion; returns its summary and provenance |
| `GET /missions/{id}/telemetry`, `/step`, `/robot-state` | recorded frames |
| `GET /missions/{id}/decisions` | every planning decision with each candidate's route and verdict |
| `GET /missions/{id}/belief?index=` | whole-map belief snapshot beside ground truth |
| `GET /missions/{id}/probe?row=&col=&index=` | every value shown for one cell, computed by the engine |
| `GET /terrain`, `/terrain/probe` | generated terrain rasters; a cell readout before any mission |
| `GET /model-constants` | thresholds drawn on legends (slope limit, severe slip) |
| `GET /results`, `/results/available` | committed results, contrasts (primary and secondary), audit summary |
| `GET /results/paired-replay?condition=&seed=` | re-runs one confirmatory seed under both primary planners and checks each against its row |
| `GET /failures` | failure categories with rule-chosen, re-run, reproduction-checked case studies |
| `GET /sweep-point` | one Scenario Lab point, validation seeds only |
| `GET /demo-mission` | the rule-selected demonstration mission and its rule |

Vehicle models (`web/public/models/*.glb`) are built from code by
`scripts/build_vehicle_models.py` in Blender. They are illustration: the
simulator moves a point robot between cells.

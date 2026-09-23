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

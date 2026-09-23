# Methodology

## Motivation

NASA's [CADRE mission](https://www.jpl.nasa.gov/missions/cadre/) will land three small rovers on
the Moon (via IM-3, 2026) that explore cooperatively and communicate over a mesh network, making
real-time decisions without a human in the loop — because Earth-Moon communication latency and
dropout rule out remote control. That same constraint — **rovers can only coordinate with whichever
teammates are currently within radio range** — is the central experimental variable in this
project.

## Research question

> When the communication range between rovers shrinks, how much better does a swarm coordination
> policy *learned* with reinforcement learning perform at cooperative terrain exploration than
> classical decentralized swarm algorithms — and how much more resilient is it to individual rover
> failures?

## Hypothesis

A swarm of rovers using a policy trained with multi-agent-style reinforcement learning (acting
only on its own sensed map plus whatever a range-limited mesh network has relayed to it) will
achieve significantly higher **terrain coverage per unit of energy spent**, and will **degrade
more gracefully when rovers are lost**, than three classical decentralized baselines — and this
advantage will grow as communication range shrinks.

- **H0 (null):** mean final coverage (and coverage-per-energy) does not differ between algorithms.
- **H1 (alternative):** mean final coverage / coverage-per-energy differs between algorithms, and
  the RL policy's advantage over the baselines grows as `comm_radius` decreases.

## Independent variables

| Variable | Levels tested |
|---|---|
| Algorithm | `frontier`, `potential_field`, `pheromone`, `rl_policy` |
| Communication radius (cells) | e.g. 3, 6, 10, 16, 24, 40 |
| Swarm size | e.g. 1, 2, 4, 6, 8 rovers |
| Rover failure rate | e.g. 0%, 25%, 50% of the swarm disabled partway through the run |

## Dependent variables

- **Final coverage** — fraction of non-hazard terrain cells sensed by any rover by episode end.
- **Coverage per energy** — final coverage divided by total battery consumed across the swarm
  (a proxy for mission efficiency: a mission that maps less area per watt-hour is worse even if it
  eventually covers the same ground).
- **Rovers alive at episode end.**
- **Steps taken** (time to finish, or to hit the step cap).

## The simulation

Terrain (`src/lunar_swarm/terrain.py`) is procedurally generated per random seed: rolling
regolith noise, several bowl-shaped craters with raised rims (rim rocks are a hazard), a slope map
derived from the elevation gradient (cells steeper than the rover's slope limit are impassable),
and permanently shadowed regions on crater floors facing away from a fixed low sun angle — modeled
on real polar lunar craters like Shackleton, where PSRs never receive sunlight and therefore never
solar-recharge a rover that sits in one.

Each rover (`src/lunar_swarm/rover.py`) only knows what it has personally sensed (within
`sensor_radius`) plus whatever another rover has relayed to it over the mesh network
(`comms.py`) — direct and multi-hop, but only while within `comm_radius` of a chain of
teammates. This is what makes `comm_radius` a meaningful independent variable: shrink it and
rovers act on staler, more local information, exactly as CADRE-style missions must.

## Algorithms compared

- **`frontier`** — greedy nearest-frontier exploration (move toward the closest known cell that
  borders unknown territory). No explicit coordination between rovers.
- **`potential_field`** — artificial potential fields: attraction toward frontiers, repulsion from
  other rovers (spreads the swarm out) and from known hazards.
- **`pheromone`** — ant-colony-style stigmergy: rovers deposit decaying "visited" pheromone on the
  terrain and steer toward the lowest-pheromone, least-explored nearby cell. Coordination happens
  through the shared environment, not radio communication.
- **`rl_policy`** — a PPO-trained neural network (Stable-Baselines3) acting on a fixed-size
  egocentric observation (local known/unknown/hazard patch, battery level, nearest-teammate
  direction, nearest-frontier direction, time remaining).

All four act through the same discrete 8-direction-plus-stay action space and the same
`SwarmEnv.step()` loop, so differences in outcome reflect differences in decision-making, not
differences in the world they're tested in.

## A disclosed simplification in RL training

Training a fully decentralized *self-play* multi-agent policy from scratch is a research-level
undertaking on its own. This project uses a standard simplification: during training, one rover
(the "learner") is controlled by the policy being trained, while its swarm-mates follow the
`frontier` baseline. At **evaluation time**, every rover in the swarm runs its own independent copy
of the same trained network — true decentralized execution, since each copy only ever sees that
one rover's own local knowledge. This is a legitimate way to bootstrap a parameter-shared
decentralized policy without full self-play, and it keeps training time low enough to run on a
laptop CPU (see `src/lunar_swarm/rl/train.py`). A natural extension (noted for future work) is
iterative self-play, where teammates are periodically replaced with snapshots of the
policy itself as it improves.

## Experimental design

`src/lunar_swarm/experiments/runner.py` runs a full sweep: every algorithm × every combination of
the independent variables × `n_seeds` independent random terrains, each a completely fresh
simulation. Results are saved to `data/results/*.csv`, one row per trial.

## Statistics

`src/lunar_swarm/experiments/stats.py` provides:
- **One-way ANOVA** across algorithms on a chosen metric.
- **Pairwise Welch's t-tests** (does not assume equal variance) between every pair of algorithms.

Both are exposed interactively in the Streamlit **Results Explorer** page.

## Limitations

- 2D grid world, not full 3D terrain/kinematics — appropriate for a coverage/coordination study,
  not for e.g. wheel-terrain interaction.
- RL training uses a heuristic-teammate simplification rather than full self-play (see above).
- Communication model is binary in-range/out-of-range with instantaneous relay within a connected
  mesh component; real radios have continuous signal degradation and per-hop latency.

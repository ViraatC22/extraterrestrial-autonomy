# Methodology

> **The authoritative, complete methodology — with all equations, the full
> experimental design, and the statistical treatment — is the paper:
> [`paper/paper.tex`](../paper/paper.tex) (compiled: `paper/paper.pdf`).**
> This file is a short orientation so you can find your way around the code.
> Where the two ever disagree, the paper and the code are correct and this
> file is stale — please fix it.

## The question

NASA's [CADRE mission](https://www.jpl.nasa.gov/missions/cadre/) will put three
cooperating rovers and a base station on the Moon (aboard Intuitive Machines
IM-3, targeting Reiner Gamma; launch currently scheduled for early 2027). They
must coordinate over a range-limited mesh network with no human in the loop,
because Earth–Moon light time rules out teleoperation.

**Research question.** As the inter-rover communication radius shrinks, how does
a reinforcement-learning coordination policy compare against classical
decentralized swarm heuristics at exploring terrain — and which degrades more
gracefully when rovers fail?

## Hypotheses

- **H1** — the four policies differ in mean final coverage.
- **H2** — the gap between policies *grows as communication radius shrinks*
  (formally: an algorithm × comm-radius **interaction**, not a main effect).
- **H3** — the policies differ in how gracefully they degrade under rover loss.

## Where things live

| Concern | File |
|---|---|
| Terrain generation (craters, slopes, hazards, PSRs) | `src/lunar_swarm/terrain.py` |
| Rover state, movement, battery, energy accounting | `src/lunar_swarm/rover.py` |
| Range-limited multi-hop mesh networking | `src/lunar_swarm/comms.py` |
| Simulation loop, metrics, failure injection | `src/lunar_swarm/environment.py` |
| Classical baselines | `src/lunar_swarm/baselines/` |
| RL training env, training script, deployment policy | `src/lunar_swarm/rl/` |
| Batch experiment runner | `src/lunar_swarm/experiments/runner.py` |
| Statistics (paired tests, Holm, ANOVA) | `src/lunar_swarm/experiments/stats.py` |
| Paper tables/figures generator | `scripts/make_paper_assets.py` |

## Design decisions that matter for validity

**Matched terrain (randomized block design).** Terrain and initial rover
placement are deterministic functions of the trial seed alone, so every
algorithm runs on bit-identical terrain within a condition. This is why the
analysis is *paired*, not independent-samples — asserted by
`tests/test_runner.py`.

**Train/test seed separation.** RL training draws a fresh terrain every episode
from seeds in `[100000, 1000000)`; evaluation uses seeds `0..N-1`. The pools are
disjoint by construction, so no reported result was measured on a training map.

**Energy is measured, not inferred.** `energy_spent` accumulates the actual
battery draw per action. It is *not* the end-of-episode battery deficit, because
solar recharge would make that understate real expenditure. Rover survival is
reported as its own separate dependent variable rather than folded into energy.

**RL training simplification (disclosed).** During training one learner rover is
embedded among frontier-following teammates; at evaluation every rover runs an
independent copy of the trained network. This is a best-response-to-heuristic
approximation of self-play and is a genuine limitation, discussed in the paper.

**Multiple trained policies.** Three policies are trained from different RL
seeds and all are evaluated, because a single training run is weak evidence.

## Two defects found and fixed during development

Both produced plausible-looking but wrong numbers, and both are now covered by
regression tests. They are documented in the paper's *Threats to Validity*.

1. **Policies could get permanently wedged.** The steering rule committed to a
   single best heading; if it pointed at a hazard the move was rejected and the
   policy re-issued the identical rejected move forever, yielding near-zero
   coverage. Fixed by falling through to the next-best *traversable* heading
   (`best_traversable_action`); guarded by `tests/test_baselines.py`.
2. **The RL policy trained on a single map.** Environments used a fixed config
   seed, so after the first episode every episode regenerated the same terrain —
   and evaluation seeds overlapped it. Fixed by resampling terrain per episode
   from a disjoint training pool.

## Reproducing the results

```bash
python -m lunar_swarm.rl.train --timesteps 500000 --seed 0 --out-name ppo_seed0
python scripts/run_paper_experiments.py
python scripts/make_paper_assets.py
tectonic paper/paper.tex
```

Every number and figure in the paper is emitted by `make_paper_assets.py` from
the committed CSVs in `data/results/`; none is typed by hand.

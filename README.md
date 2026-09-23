# Lunar Swarm Nav

**Decentralized vs. learned swarm coordination for communication-constrained lunar surface
exploration.** A science fair project (Robotics & Intelligent Machines) built around a simulated
swarm of rovers exploring procedurally generated lunar terrain, comparing a reinforcement-learning
policy against classical decentralized swarm algorithms as communication range, swarm size, and
rover-failure rate change.

Motivated by NASA's [CADRE mission](https://www.jpl.nasa.gov/missions/cadre/) — three autonomous
rovers landing on the Moon (launch currently scheduled for early 2027) that must coordinate over a mesh network with no real-time human
control, because Earth-Moon communication has latency and dropout. See
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the full hypothesis, experimental design, and
statistics, and [`docs/REFERENCES.md`](docs/REFERENCES.md) for the research this builds on.

## What's here

- **Simulation core** (`src/lunar_swarm/`) — procedural lunar terrain (craters, hazard slopes,
  permanently shadowed regions), rovers with limited sensing/battery/communication, and a
  range-limited mesh network.
- **Four algorithms** — three classical decentralized baselines (`frontier`, `potential_field`,
  `pheromone`) and one policy trained with reinforcement learning (`rl_policy`, PPO via
  Stable-Baselines3).
- **Experiment runner + statistics** (`src/lunar_swarm/experiments/`) — batch sweeps across
  conditions/seeds, ANOVA and pairwise t-tests.
- **Streamlit dashboard** (`app/`) — live simulation viewer, experiment runner, and results
  explorer with interactive plots.

## Setup

Requires Python 3.10+.

> **Note:** this project folder's name contains a `/` (shown by Finder as `26/27`, stored on disk
> as `26:27`). Colons are path separators on Unix, so `python -m venv` refuses to create a virtual
> environment *inside* this folder. Put the venv anywhere else instead, e.g.:

```bash
python3 -m venv ~/.venvs/lunar-swarm-nav
source ~/.venvs/lunar-swarm-nav/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Run the dashboard

```bash
source ~/.venvs/lunar-swarm-nav/bin/activate
streamlit run app/streamlit_app.py
```

Opens with three pages: **Live Simulation** (watch one run step by step), **Run Experiments**
(configure and launch a batch sweep), **Results Explorer** (summary stats, plots, ANOVA/t-tests on
any saved sweep).

## Train the RL policy

```bash
python -m lunar_swarm.rl.train --timesteps 300000
```

Saves to `models/ppo_lunar_swarm.zip`. On a laptop CPU this takes roughly 10-30 minutes; a smaller
`--timesteps` is fine for quick iteration. See `python -m lunar_swarm.rl.train --help` for all
options (swarm size, terrain size, communication radius used during training, etc).

## Run the default experiment sweep from the terminal

```bash
python scripts/run_default_sweep.py
```

Regenerates `data/results/sweep_results.csv` — the same thing the "Run Experiments" dashboard page
does, without the UI.

## Run the tests

```bash
python -m pytest tests/ -v
```

## Project structure

```
src/lunar_swarm/
  terrain.py          procedural lunar terrain generation
  rover.py             single-rover agent state and movement
  comms.py              range-limited mesh networking between rovers
  environment.py        the multi-rover simulation loop (SwarmEnv)
  algorithms.py          registry combining baselines + trained RL models
  baselines/             frontier, potential-field, and pheromone (ACO-style) policies
  rl/                     Gymnasium training wrapper, PPO training script, deployment policy
  experiments/            batch sweep runner + statistics (ANOVA, t-tests)
  viz/                     matplotlib rendering for the live-simulation view
app/                      Streamlit dashboard (3 pages)
scripts/                  terminal convenience scripts
tests/                     pytest suite
docs/                      methodology, references
models/                    trained RL model checkpoints (.zip)
data/results/               saved experiment sweep CSVs
```

## License

MIT — see [`LICENSE`](LICENSE).

# EXONAUT

**Adaptive risk-aware autonomy for robotic exploration of uncertain extraterrestrial terrain.**

EXONAUT is a reproducible simulation study of a planetary rover that must collect science value
and return safely while terrain behavior, energy use, sensing, and hardware health are uncertain.
The central experiment compares three planners on matched procedural worlds:

1. distance-only A*;
2. fixed risk-aware A*; and
3. adaptive risk-aware A*, which updates a Bayesian slip model from driving experience.

The robot begins with a prior calibrated on lunar training terrains. The out-of-distribution test
sends that unchanged prior to Martian terrains whose class frequencies and slip statistics differ.
The study asks whether online adaptation preserves science return and mission completion when the
deployment environment differs from the calibration environment.

The earlier multi-rover lunar-swarm study remains available under `src/exonaut/multiagent/` for
reproducibility, but it is no longer the primary research question.

## Current evidence status

- The seed protocol and lunar/Martian priors are frozen and checksummed.
- The implementation and regression suite pass 66 tests.
- A 60-mission pilot is committed under `data/results/exonaut_pilot.csv`.
- Pilot results are descriptive only: four matched seeds per condition are insufficient for a
  confirmatory claim.
- The preregistered 50-seed-per-condition run has not yet been designated as final evidence.

The EXONAUT paper is `paper/exonaut.tex`. Every number it reports is generated from the
row-level results CSV by `scripts/make_exonaut_paper_assets.py`; no value is typed into the
document. The completed write-up for the earlier swarm study is kept separately under
`paper/swarm_extension/` so its figures can never be mistaken for EXONAUT results.

## Setup

Python 3.10 or newer is required. Because this repository's folder name contains a colon, create
the virtual environment outside the repository:

```bash
python3 -m venv ~/.venvs/exonaut
source ~/.venvs/exonaut/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Reproduce the research workflow

Verify the frozen seed protocol and run the tests:

```bash
python -c "from exonaut.experiments.protocol import verify_splits; print(verify_splits())"
python -m pytest -q
```

Re-run the documented pilot:

```bash
python scripts/run_exonaut_experiments.py --pilot
python scripts/make_exonaut_paper_assets.py
```

Run the preregistered confirmatory design:

```bash
python scripts/run_exonaut_experiments.py \
  --config experiments/configs/exonaut_main.json
```

Compile the paper with Tectonic:

```bash
tectonic -X compile paper/paper.tex --outdir paper
```

Do not overwrite the confirmatory result after inspecting it. If the method changes, record a new
protocol/version and run it on new seeds.

## Repository map

```text
src/exonaut/
  autonomy/       Bayesian world model, risk composition, mission decisions
  environments/   Moon/Mars procedural ground-truth generators
  planners/       shared A* search and the three planner treatments
  robot/          sensing, energy, motion, slip, embedding, and faults
  experiments/    frozen seeds, batch runner, statistics, metadata
  multiagent/     archived lunar-swarm experiment
  simulation.py   one complete deterministic rover mission
experiments/configs/  pilot and confirmatory designs
data/processed/       calibrated priors
data/splits/          immutable seed protocol
data/results/         row-level results and provenance sidecars
docs/                 architecture, methodology, preregistration, research log
paper/                LaTeX source, generated assets, and compiled PDF
tests/                scientific-integrity and regression tests
```

## Scientific scope

This is a controlled 2.5-D autonomy testbed, not a flight dynamics model or a prediction of any
specific lunar or Martian mission. Terrain parameters are chosen to create identifiable risk and
domain-shift regimes. Claims are restricted to comparative behavior inside this simulator.

See `docs/METHODOLOGY.md`, `docs/PREREGISTRATION.md`, and `docs/RESEARCH_LOG.md` before interpreting
or extending the results.

## License

MIT. See `LICENSE`.

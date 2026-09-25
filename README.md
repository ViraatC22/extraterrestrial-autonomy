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

- The seed protocol and lunar/Martian priors are frozen and checksummed; eight seeds consumed by an
  early engineering pilot are permanently quarantined and excluded from all confirmatory results.
- The implementation and regression suite pass 66 tests.
- The confirmatory run is complete: 750 missions on held-out seeds, committed as
  `data/results/exonaut_main.csv` with a metadata sidecar recording the git commit, split checksum,
  quarantine list and library versions.

### Headline outcome

Adaptation was **neutral in distribution** (lunar success 0.92 vs 0.90) and did **not** improve
science return under domain shift, contradicting hypothesis H2. The one contrast that survived Holm
correction, success in the condition labelled "hardware faults" (0.26 → 0.46), **is not a fault
effect**. A post-hoc audit found faults fired in only 16-26% of those missions, and in neither
mission on 5 of the 10 seeds that drove the result, so H3 is not supported either. What remains is
a descriptive, untested pattern: adaptation trades a little science for survival. A second audit
found the adaptive learner is about 7× overconfident. See `docs/RESEARCH_LOG.md` and
`scripts/audit_confirmatory.py`.

An unpredicted result: distance-only A* had the highest Martian success rate in three of four
conditions while returning the least science, indicating that the risk formulation prices caution
as free when nearly all terrain is hazardous.

`docs/PREREGISTRATION.md` is a confirmatory analysis plan, not a pre-registration; the reasons and
the full timeline are in `docs/RESEARCH_LOG.md`.

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

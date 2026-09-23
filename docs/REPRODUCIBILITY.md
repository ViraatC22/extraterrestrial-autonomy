# Reproducibility

Every figure and number in `paper/exonaut.tex` is regenerable from the files in
this repository. Nothing is typed into the paper by hand.

## Chain of custody

```
config (configs/*.yaml)
        +
seed splits (data/splits/seed_splits.json, checksummed)
        ↓
run_exonaut_experiments.py
        ↓
data/results/<run>.parquet   ← archival, dtypes preserved
data/results/<run>.csv       ← same DataFrame, for inspection
data/results/<run>.metadata.json
        ↓
make_exonaut_paper_assets.py
        ↓
paper/tables/*.tex  +  paper/figures/*.pdf  +  macros
        ↓
paper/exonaut.tex  →  paper/exonaut.pdf
```

Every result file carries a metadata sidecar recording:

- `run_id` — a digest of the design, so an identical design yields an identical
  ID and a changed design cannot overwrite an earlier result under the same name
- `git.commit`, `git.branch`, `git.dirty_worktree`, `git.dirty_files`
- `seed_split_checksum` and `seed_split_created`
- `quarantined_seeds` — terrains excluded because they were observed before the
  protocol was frozen
- `software` — Python, NumPy, SciPy, pandas, and where present torch,
  scikit-learn, statsmodels, pyarrow, plus the platform string

## Full rebuild

```bash
python3 -m venv ~/.venvs/exonaut
source ~/.venvs/exonaut/bin/activate
pip install -r requirements.txt      # or requirements-lock.txt for exact pins
pip install -e .

python scripts/freeze_seed_protocol.py       # once; refuses to overwrite
python scripts/calibrate_priors.py           # priors from TRAIN seeds only
python scripts/run_exonaut_experiments.py    # confirmatory sweep (~20 min, 9 workers)
python scripts/make_exonaut_paper_assets.py  # tables, figures, macros
cd paper && tectonic exonaut.tex
```

## Determinism

A trial is fully determined by its configuration and its seed. That covers the
terrain, the science-target layout, the fault schedule, and every slip draw, so
each planner faces an identical world within a condition. `tests/` asserts that
a repeated sweep returns a byte-identical frame and that parallel and serial
execution agree.

Determinism is *not* claimed across differing NumPy major versions or
platforms; the recorded `software` block exists so such a difference is
detectable rather than silent.

## What "dirty worktree" means in a sidecar

`dirty_worktree: true` means files were modified relative to the recorded
commit when the run finished. It does not automatically invalidate the run, but
it means the commit alone does not describe what executed, so `dirty_files`
is recorded too. For the committed confirmatory run, `git diff` between the
run-start commit and the recorded commit touches only
`experiments/analysis.py`, which the sweep does not import; every simulation,
planner, autonomy, robot, environment and runner module was byte-identical
throughout. `docs/RESEARCH_LOG.md` records this check.

## Verifying the protocol has not moved

```bash
python -c "from exonaut.experiments.protocol import verify_splits; print(verify_splits())"
```

`load_splits()` raises if the split file no longer matches its recorded
checksum. CI runs a dedicated `protocol-integrity` job that re-verifies the
checksum and asserts no quarantined seed is reachable from a confirmatory
split, so tampering fails the build rather than passing quietly.

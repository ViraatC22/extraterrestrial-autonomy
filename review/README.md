# EXONAUT — reviewer package

Everything needed to review the EXONAUT application without prior context:
screenshots of every page, real API responses, a one-command launcher, and a
map of where each piece of code lives.

**Project in one sentence.** A simulated planetary rover carries a terrain
model calibrated on the Moon, is sent to Mars where the ground behaves
differently, and we test whether a planner that revises its terrain model from
its own driving does better than one that doesn't.

**Headline result (from 750 missions on held-out terrain).** Adaptation did not
improve science return (H2 not supported). One contrast survived correction:
success in the "hardware faults" condition, 0.26 → 0.46, Holm p = 0.020. But
a later audit showed faults fired in only 16-26% of those missions, so it is
not a fault effect (H3 not supported). See `docs/RESEARCH_LOG.md`.

---

## 1. Screenshots (`screenshots/`)

All captured from the running app at 1600×1000 by `capture_screenshots.py`.

| File | Page | What to look at |
|---|---|---|
| `01_mission_control_idle.png` | Mission Control | Setup controls; the frozen seed protocol panel (bottom left) |
| `02_mission_control_launched.png` | Mission Control | 3D Mars terrain, rover route (cyan), targets, live telemetry, belief-vs-truth bars |
| `03_mission_control_layer_slope.png` | Mission Control | Same mission with the slope layer |
| `03_mission_control_layer_light.png` | Mission Control | Same mission with the illumination layer |
| `04_autonomy_inspector.png` | Autonomy Inspector | Every candidate target the planner scored, and which it picked |
| `05_experiments.png` | Experiments | Confirmatory statistics, read from the committed results file |
| `06_failure_analysis.png` | Failure Analysis | Failure modes, and where the proposed method loses |
| `07_scenario_lab_setup.png` | Scenario Lab | Sweep configuration |
| `08_scenario_lab_results.png` | Scenario Lab | A small exploratory sweep (2 missions per point) |

To regenerate them (both servers must be running):
`python review/capture_screenshots.py`

## 2. Real API responses (`api_samples/`)

These are captured responses, not hand-written examples.

| File | Endpoint |
|---|---|
| `health.json` | `GET /health` |
| `planners.json` | `GET /planners` |
| `splits.json` | `GET /splits`: frozen seed ranges, with quarantined seeds removed |
| `results_available.json` | `GET /results/available` |
| `results_exonaut_main.json` | `GET /results?name=exonaut_main`: the confirmatory statistics shown on the Experiments page |
| `start_mission_response.json` | `POST /start-mission` (Mars, adaptive planner, seed 200000) |
| `telemetry_excerpt.json` | `GET /missions/{id}/telemetry`: first 3 frames and the last one, including the per-candidate decision records |

## 3. Running it yourself

```bash
bash review/run_app.sh
```

This starts the engine at http://127.0.0.1:8000 (interactive API docs at `/docs`)
and the web app at http://localhost:3000. It expects a Python virtualenv at
`~/.venvs/lunar-swarm-nav`, or wherever `EXONAUT_VENV` points. The script
prints setup steps if it can't find one.

Checks:

```bash
pytest tests/ -q                       # 94 tests
ruff check src scripts tests app       # Python lint
cd web && npm run lint && npm run typecheck && npm run build
```

## 4. Architecture

```
web/  (Next.js + React Three Fiber)  ──HTTP──▶  src/exonaut/api/  (FastAPI)
                                                    │
                                     src/exonaut/simulation.py  (mission loop)
            ┌───────────────┬───────────────┬───────┴───────┬──────────────┐
      environments/      robot/         autonomy/        planners/     experiments/
      Moon, Mars terrain  slip, energy,  world model,     A*, Dijkstra,  seed protocol,
      generation          sensors,       risk, mission    D* Lite, risk- runner, stats,
                          faults         manager, priors  aware, adaptive provenance
```

The browser never does any science. Every number on the Experiments and
Failure Analysis pages comes from `data/results/exonaut_main.csv` through the
API, and those are the same files the paper (`paper/exonaut.tex`) is generated
from.

| Concern | Where |
|---|---|
| Mission loop | `src/exonaut/simulation.py` |
| Belief update (the "adaptation") | `src/exonaut/autonomy/world_model.py`: `AdaptiveWorldModel.ingest_slip` |
| Risk / P(failure) | `src/exonaut/autonomy/risk.py` |
| Target selection + candidate records | `src/exonaut/autonomy/mission_manager.py`: `select_objective` |
| Planners | `src/exonaut/planners/` |
| Seed protocol + quarantine | `src/exonaut/experiments/protocol.py`, `data/splits/` |
| Confirmatory statistics | `src/exonaut/experiments/analysis.py` |
| API | `src/exonaut/api/` |
| 3D scene | `web/src/components/MissionScene.tsx` |
| Pages | `web/src/app/{page,inspector,scenario,experiments,failures}/` |
| Research history, including mistakes | `docs/RESEARCH_LOG.md` |

## 5. Things a reviewer should push on

These came up while making this package. I've written them down rather than
cleaning them up, because they're the questions a judge would ask.

1. **"SUCCESS" with zero science.** `02_mission_control_launched.png` shows a
   green SUCCESS badge while science is 0.00, targets 0, and interventions 15.
   In this project "success" means *returned to the lander alive*, and science
   is a separate measure. That definition is intentional and stated in the
   paper, but a big green badge on a mission that collected nothing may read
   as misleading. Consider showing science next to the badge.
2. **The belief overshoots the truth, and the learner is overconfident.**
   The rover believes loose-fines slip is 0.776 against a true 0.620. The
   cause is diagnosed (`docs/RESEARCH_LOG.md`, 2026-09-25). That belief rests
   on only 3 readings, and the learning rule treats each reading as nearly
   noise-free. On 40 validation missions its 95% intervals contain the truth
   only 20% of the time. A corrected rule reaches 85%. The confirmatory result
   was produced with the uncorrected rule. An earlier guess here ("selection
   bias from retried cells") was wrong.
3. **Scenario Lab values look too uniform.** Investigated. Fault rates 0.5
   and 1 often draw the same number of faults from a shared random stream,
   which gives identical missions. A related design weakness: a zero fault
   rate also shifts every later slip draw. Primary results are unaffected;
   details are in `docs/RESEARCH_LOG.md` (2026-09-25).
4. **Pre-registration status.** `docs/PREREGISTRATION.md` was written after the
   adaptive planner existed and after an 8-seed pilot. The document says so,
   and those seeds are quarantined. It's a confirmatory analysis plan, not a
   true pre-registration. Full timeline is in `docs/RESEARCH_LOG.md`.
5. **Known dev-only console error.** On first page load, one
   `Cannot read properties of undefined (reading 'length')` appears from
   `next/dist/compiled` (the dev overlay). It doesn't recur during use and
   pages work. It hasn't been checked against a production build.
6. **Folder name contains a colon** (`Science Fair 26:27`). That's why npm
   scripts call `node` directly, and it will break some JS tooling.

## 6. Fixed while preparing this package

- The Mission Control header divided the mission timestep by the number of
  recorded telemetry frames (showing e.g. `STEP 0055/0040`). Steps spent
  waiting on mission control don't produce frames, so these are different
  units. It now divides by total mission steps (`0055/0056`).

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

Captured from the running app at 1600×1000 by `capture_screenshots.py`.

| File | What it shows |
|---|---|
| `01_mission_control_surface.png` | Mars surface. Rocks sit only on cells the simulator classes as rocky or rim talus; the outline marks the edge of the simulated area |
| `02_camera_chase.png` / `03_camera_rover_pov.png` | Chase and rover-mast cameras |
| `04_camera_planner_candidate_routes.png` | Planner view: every route evaluated at the current decision, with P(fail) and the risk budget |
| `05_layer_knowledge.png` | What the rover has seen: unexplored (dark), confident (teal), uncertain (amber) |
| `06_layer_belief_error.png` | Belief minus truth. Blue = the rover thinks ground is better than it is |
| `07_layer_risk.png` | The planner's P(entry ends mission), log scale |
| `08_terrain_probe.png` | Hover probe; every value tagged GENERATED / SIMULATED / INFERRED / ASSUMED |
| `09_presentation_mode.png` | Full-screen demo mode with live captions |
| `10_autonomy_inspector.png` | Decision rule, risk-budget check, and every candidate's scores |
| `11_experiments_intervals.png` / `12_experiments_pareto_forest_seeds.png` | Confirmatory results as plots, with intervals from the engine |
| `13_failure_case_studies.png` | One verified, replayable case per failure mode |
| `14_case_study_replay.png` | A case study opened in Mission Control, with provenance |
| `15_scenario_lab_sensitivity.png` | Sensitivity sweep on validation seeds, 95% bands |

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

Found while building this interface. Each one is logged with numbers in
`docs/RESEARCH_LOG.md`, and each is reflected in the paper.

1. **H3 was wrong, and has been corrected.** The one significant result
   (success in the "hardware faults" condition, 0.26 → 0.46) was presented
   as fault tolerance. `scripts/audit_confirmatory.py` shows faults fired in
   only 16% of adaptive and 26% of fixed missions, and in neither mission on 5
   of the 10 seeds that drove the result. It is now reported as not supported.
2. **The adaptive learner is ~7× overconfident.** Its 95% intervals contain
   the true slip only 20% of the time; a variance-corrected update reaches 52%. All
   confirmatory results use the flawed rule.
3. **Intervention relaxation ratchets.** Every request for ground help raises
   the hazard threshold by 0.15, up to 0.95, and it never resets.
4. **Most timeouts are a livelock.** In 35 of 44 timeouts, the rover sat at
   the lander requesting help hundreds of times.
5. **One random stream serves everything,** so changing the fault rate also
   changes every slip draw. Paired contrasts are unaffected; cross-condition
   comparisons are noisier than they should be.
6. **Pre-registration status.** `docs/PREREGISTRATION.md` is a confirmatory
   analysis plan written after the method and an 8-seed pilot existed. It says
   so.

None of the engine defects have been fixed. Fixing them and re-running on the
same held-out seeds would be post-hoc tuning. The proposed route is a
separately declared v2 study on held-out seeds not yet used.

## 6. Design rules the interface follows

- The browser computes no statistics. Intervals and contrasts come from
  `src/exonaut/experiments/analysis.py` through the API.
- Recording data for the interface never changes a mission. Outcomes are
  verified byte-identical, and every case study re-run is checked against its
  committed row.
- Exploratory sweeps use validation seeds chosen by the engine, never by the
  browser.
- Visual-only elements (sub-cell texture, land beyond the map) are labelled
  as such.

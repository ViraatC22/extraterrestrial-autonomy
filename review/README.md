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
a later audit showed faults rarely fired in those missions, so it is not a
fault effect (H3 not supported). See `docs/RESEARCH_LOG.md` and the
Experiments page, which quotes the audit's numbers from its table.

---

## 1. Screenshots (`screenshots/`)

Captured from the running app at 1600×1000 by `capture_screenshots.py`.

| File | What it shows |
|---|---|
| `01_mission_control_surface.png` | Mars surface mid-mission. Rocks sit only on cells the simulator classes as rocky or rim talus; the outline marks the edge of the simulated area; a ring marks the (to-scale) rover in overview cameras |
| `02_camera_chase.png` | Spring-arm chase camera: the arm shortens when terrain or the lander would block it; labels fade as the camera closes in |
| `03_camera_navcam.png` | The rover's mast navigation camera, with heading, sensing range and local slope from the engine. The readout says the rendered frustum is not the simulated sensor (a radius) |
| `04_demo_mission_planner_view.png` | The rule-selected demonstration mission at its adaptation event: selected route solid green, feasible alternatives dashed grey, routes over the risk budget dashed red, with a route key |
| `05_layer_knowledge.png` | What the rover has seen, with a quantitative uncertainty scale |
| `06_layer_belief_error.png` | Belief minus truth on a fixed −0.5…+0.5 scale (an evaluation the rover cannot make) |
| `07_layer_risk_with_budget.png` | Per-cell P(entry ends mission), log scale, with the mission's risk budget ε marked |
| `08_terrain_probe_compare.png` | Two pinned cells compared; every row computed by the engine and tagged GENERATED / SIMULATED / INFERRED / ASSUMED |
| `09_presentation_mode.png` | Full-screen presenting view, keyboard-driven (1–5 camera, space, arrows, L layer, T planner, Esc) |
| `10_focus_mode.png` | Side columns collapsed so the world fills the page |
| `11_paired_replay_adaptive.png` / `12_paired_replay_fixed.png` | One committed confirmatory seed replayed under both planners on the same terrain; each run checked against its committed row |
| `13_autonomy_inspector_calculation.png` | "Show calculation": equation → the engine's numbers → the decision |
| `14_experiments_tiers_intervals.png` | Every panel tagged PRIMARY / SECONDARY / DESCRIPTIVE / EXPLORATORY / POST-HOC |
| `15_experiments_effects_seeds.png` | Effect sizes and intervals first, Holm-adjusted p underneath; seed-by-seed plot where a click replays the seed |
| `16_experiments_secondary.png` | Secondary contrasts against the distance-only control |
| `17_failure_case_studies.png` / `18_case_study_replay.png` | One verified, replayable case per failure mode, and one opened in Mission Control |
| `19_scenario_lab_sensitivity.png` | Sensitivity sweep on validation seeds, 95% bands; missions per point selectable |
| `model_rover.png` / `model_lander.png` | Blender renders of the vehicle models (built from code by `scripts/build_vehicle_models.py`) |

## 2. Real API responses (`api_samples/`)

These are captured responses, not hand-written examples.

| File | Endpoint |
|---|---|
| `health.json`, `planners.json`, `splits.json`, `results_available.json` | service basics; frozen seed ranges with quarantined seeds removed |
| `results_exonaut_main.json` | `GET /results`: confirmatory statistics, primary and secondary contrasts, and the fault-exposure audit |
| `start_mission_response.json` | `POST /start-mission` (Mars, adaptive planner, seed 200000) |
| `telemetry_excerpt.json` | `GET /missions/{id}/telemetry`: first 3 frames and the last, including heading and local slope |
| `decisions_excerpt.json` | `GET /missions/{id}/decisions`: two decisions, each candidate with its budget verdict and utility rank (routes truncated) |
| `probe.json` | `GET /missions/{id}/probe`: every value the probe shows for one cell |
| `model_constants.json` | `GET /model-constants`: thresholds drawn on legends |
| `paired_replay.json` | `GET /results/paired-replay`: both planners on one confirmatory seed, with reproduction checks |
| `demo_mission.json` | `GET /demo-mission`: the demonstration mission, its selection rule and every seed scanned |

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
pytest tests/ -q                       # 190 tests
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
| 3D scene | `web/src/components/MissionScene.tsx`, `Vehicles.tsx`, `CameraRig.tsx` |
| Vehicle models | `scripts/build_vehicle_models.py` → `web/public/models/` |
| What the interface may and may not compute | `docs/DATA_FLOW.md` |
| Pages | `web/src/app/{page,inspector,scenario,experiments,failures}/` |
| Research history, including mistakes | `docs/RESEARCH_LOG.md` |

## 5. Things a reviewer should push on

Found while building this interface. Each one is logged with numbers in
`docs/RESEARCH_LOG.md`, and each is reflected in the paper.

1. **H3 was wrong, and has been corrected.** The one significant result
   (success in the "hardware faults" condition, 0.26 → 0.46) was presented
   as fault tolerance. `scripts/audit_confirmatory.py` shows faults fired in
   only a minority of those missions, and in neither mission on half of the
   seeds that drove the result. It is now reported as not supported.
2. **The adaptive learner is overconfident.** Its 95% intervals contain the
   true slip only about 20% of the time; a variance-corrected update reaches
   about 52%. All confirmatory results use the committed rule.
3. **Intervention relaxation ratchets** in v1: every request for ground help
   raises the hazard threshold by 0.15, up to 0.95, and it never resets.
4. **Most v1 timeouts are a livelock**: the rover sat at the lander requesting
   help hundreds of times.
5. **One random stream serves everything** in v1, so changing the fault rate
   also changes every slip draw.
6. **Pre-registration status.** `docs/PREREGISTRATION.md` is a confirmatory
   analysis plan written after the method and an 8-seed pilot existed. It says
   so.

The five engine defects are fixed in an engine profile `v2`, selectable in the
interface. v1 stays the default and still reproduces all 750 committed
missions. v2 has only been explored on validation seeds (`docs/EXPLORATION_V2.md`):
the fixes work, and adaptation's survival advantage largely disappears. A v2
confirmatory study is drafted but not frozen (`docs/V2_VALIDATION_PLAN.md`);
the decisions it needs are listed there.

## 6. Design rules the interface follows

- **The browser derives nothing it displays.** Every number, verdict and
  threshold comes from the engine or a committed result; the frontend formats,
  colours and lays out. `docs/DATA_FLOW.md` lists the engine function behind
  each displayed quantity and the test that pins it.
- Recording data for the interface never changes a mission: all 750 committed
  missions still reproduce, and every re-run shown (case studies, paired
  replays) is checked against its committed row.
- Exploratory sweeps use validation seeds chosen by the engine, never by the
  browser. Requests that expose an unused held-out seed are logged to
  `data/splits/heldout_access_log.jsonl`, so a future study can show its seeds
  were untouched.
- One WebGL context per page for the scene, reused across presentation mode, focus mode,
  layers, cameras and paired-replay switching. `stress_webgl.py` cycles all of them against
  the production build and counts contexts: the latest result is in
  `webgl_stress_result.json` (none lost; the count stays flat).
- The demonstration mission is chosen by a written rule
  (`scripts/select_demo_mission.py`), and the interface shows the rule.
- Visual-only elements (vehicle motion between cells, wheel rotation, dust,
  sub-cell texture, land beyond the map) are labelled as such. The vehicle
  models are generic research platforms, not replicas of real spacecraft.

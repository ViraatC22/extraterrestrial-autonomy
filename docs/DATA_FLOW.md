# Interface data flow

The interface in `web/` must never show a number the research engine did not
produce. The failure this guards against is concrete: the paper says 0.0241,
Python says 0.0241, and the browser says 0.0237 because a formula was copied
into TypeScript and drifted.

```text
Python research engine (exonaut)       one implementation of every formula
        |
        v
canonical state / result objects        MissionResult, belief snapshots,
        |                               decision records, results tables
        v
FastAPI (src/exonaut/api)               serializes; computes nothing new
        |                               except via engine functions
        v
Next.js frontend (web/)                 lays out, formats, colours
```

## The rule

The frontend may **format** (rounding, percent, zero-padding), **lay out**
(bar lengths, axis positions, colour ramps) and **select** (which engine value
to show, which label an engine verdict maps to). It may not **derive** a
quantity that is then displayed as a number or a verdict.

When a view needs a derived quantity, the engine computes it with the
function the simulation itself uses, and a test pins the two together.

## Where each displayed quantity comes from

| Shown in the interface | Computed by | Pinned by |
|---|---|---|
| Telemetry: charge, slip, science, position, P(fail) last trip | `run_mission` history | `test_api_summary_matches_the_engine_directly` |
| Heading, local slope (nav cam readout) | `run_mission` history (`heading_deg`, `local_slope_deg`) | `test_frames_carry_engine_heading_and_slope` |
| Candidate energy, energy s.d., solar credit, P(fail) by cause, utility | `MissionManager.select_objective` via `risk.mission_failure_probability` | `test_frames_carry_auditable_candidate_evaluations` |
| Within risk budget, rank among feasible, selected | `MissionManager.select_objective` (`within_budget`, `feasible_rank`, `selected`) | `test_candidate_budget_verdicts_and_ranks_come_from_the_engine` |
| Belief map layers: expected slip, slip s.d., cell risk | `AdaptiveWorldModel.*_grid`, `risk.cell_risk_grid` | `test_belief_grids.py` (grid = per-cell function) |
| Routable (probe) | `AdaptiveWorldModel.believed_traversable_grid` | `test_routable_grid_matches_the_planners_own_test` |
| True mean slip (truth layer, probe, error layer) | `Terrain.true_slip_mean_grid` | `test_true_slip_grid_matches_the_simulators_draw` |
| Probe: solar harvest | `PowerSystem.recharge` | `test_probe_reports_engine_values` |
| Probe: every other row | `service.probe_payload` from terrain and the stored belief snapshot | `test_probe_reports_engine_values` |
| Legend markers: slope limit, severe-slip threshold | `/model-constants` (engine constants) | `test_model_constants_are_the_engines_own` |
| Legend marker: risk budget ε | the loaded mission's engine config | provenance |
| Experiments: intervals, contrasts, p-values, paired points | `experiments.analysis` on the committed results | `test_analysis.py`, `test_results_*` |
| Experiments: fault-exposure audit numbers | `experiments.audits.fault_exposure_stats` on the audit table | `test_results_carry_the_audit_and_both_contrast_families` |
| Failure Analysis: expected vs spent energy, error in s.d. | `api.failures.diagnostics` | `test_failure_case_studies_reproduce_their_committed_rows` |
| Paired replay outcomes and reproduction check | `/results/paired-replay` re-runs both planners | `test_paired_replay_reproduces_both_committed_rows` |
| Scenario Lab points and intervals | `api.sweep.run_point` | `test_sweep_points_use_validation_seeds_only` |
| Demonstration mission and its event | `scripts/select_demo_mission.py` output | `test_demo_mission_states_its_selection_rule` |

## Permitted frontend operations, listed

These remain in the frontend on purpose. None produces a displayed number that
the engine does not also hold.

- Formatting: `toFixed`, percent (`× 100`), zero-padded steps, `T+0014`.
- Colour and geometry: layer colour ramps (`lib/layers.ts`, `lib/palette.ts`),
  chart axes and bar lengths, the belief panel's colour tone.
- Replay captions (`lib/replay.ts`): events are detected by comparing
  consecutive engine frames (e.g. a class belief moving by more than 0.005,
  a recorded slip of 0.5 or more labelled "high"). These thresholds choose
  which moments get a caption; the numbers in the caption are the engine's.
- The rendered scene: vehicle interpolation between cells, wheel rotation,
  dust, camera placement. None of it is data and the legend says so.

## Bugs this audit found (2026-09-25)

Recorded in `RESEARCH_LOG.md`. In short: the probe's "routable" check ignored
the planner's slope test; the Failure Analysis page computed an energy error
in the browser; the Experiments verdict quoted typed audit percentages; the
API recomputed true slip with a copied formula; and a layer group labelled
"rover knows" contained ground-truth layers. All five are fixed as above.

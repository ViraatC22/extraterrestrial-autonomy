# Simulator validation checklist (pre-freeze gate for Study 2)

The v2 study may not run until every item below passes. Each item is an automated test;
`python -m pytest tests/test_simulator_validation.py tests/test_engine_v2.py
tests/test_calibration_methods.py tests/test_v2_protocol.py tests/test_v1_lock.py`
runs them all. All missions in these tests use development (train/validation) seeds.

Status on 2026-09-26: **all items pass** (see the test run recorded in the commit that
last touched this file). Two defects were found while writing the suite; both are
recorded in `RESEARCH_LOG.md` and listed at the end.

## Terrain

| Item | Test |
|---|---|
| Same seed, same terrain; different seed, different terrain | `test_terrain_is_a_deterministic_function_of_its_seed` |
| Fields in range; slope is exactly the gradient of elevation | `test_terrain_fields_are_in_range_and_slope_is_derived_from_elevation` |
| Every cell steeper than the limit is a hazard; hazard is not most of the map | `test_every_over_steep_cell_is_a_hazard` |
| Class frequencies differ between bodies as the design requires (Mars loose fines > 2x Moon) and every body shows at least 4 classes | `test_class_frequencies_differ_between_bodies_as_the_design_requires` |

## Motion

| Item | Test |
|---|---|
| Distance travelled equals the recorded path length (v1 and v2) | `test_distance_travelled_equals_the_recorded_path_length` |
| The rover never stands on a hazard or over-steep cell | `test_rover_never_occupies_hazardous_or_over_steep_ground` |
| Slip >= 0.80 gives no progress; three in a row immobilize | `test_severe_slip_stops_progress_and_three_in_a_row_immobilize` |
| Slip just under 0.80 still moves | `test_slip_just_below_the_severe_threshold_still_moves` |
| Success means home with every target resolved | `test_success_means_home_with_every_target_resolved` |
| No help requests while parked at the lander (v2) | `test_v2_never_requests_help_while_parked_at_the_lander`, `test_v2_removes_the_lander_livelock` |

## Energy

| Item | Test |
|---|---|
| Final charge = capacity - all draws + all harvest (v1 and v2) | `test_energy_accounting_balances` |
| Locomotion cost is the documented formula and monotone in slip, slope, gravity | `test_locomotion_cost_is_the_documented_formula` |
| Solar harvest = rate x illumination x panel efficiency, capped at capacity | `test_solar_harvest_is_rate_times_illumination_times_efficiency_capped_at_capacity` |
| A draw larger than the charge is refused; missions can end in exhaustion | `test_a_draw_larger_than_the_charge_is_refused_and_ends_in_exhaustion` |
| Energy risk is taken against charge minus the reserve | `test_energy_risk_holds_back_the_reserve` |
| The planner's expected energy uses the rover's own physics at the believed slip | `test_planner_energy_estimate_uses_the_same_physics_as_the_rover` |

## Slip and learning

| Item | Test |
|---|---|
| Slip draws have the mean of N(cell mean, class sd) clipped to [0, 0.995] | `test_slip_draws_follow_the_cell_class_distribution` |
| Slip draws use their own random stream (v2) | `test_v2_streams_isolate_faults_from_slip_draws` |
| The class posterior is the closed-form conjugate update and order-free | `test_class_belief_is_the_closed_form_conjugate_posterior_and_order_free` |
| v2 per-reading variance includes class dispersion | `test_v2_calibrated_update_moves_less_on_one_reading` |
| Calibration scale changes reported uncertainty only, never the learned mean | `test_epistemic_scale_multiplies_reported_uncertainty_and_nothing_else` |
| Confusion-aware assignment: weights are a distribution, misread cells do not contaminate rare classes, unit weights reproduce the ordinary update | `tests/test_calibration_methods.py` |

## Faults

| Item | Test |
|---|---|
| Faults fall inside the mission window (v2) | `test_v2_faults_are_scheduled_inside_the_window` |
| Faults have their own stream; changing the fault rate changes no slip draw (v2) | `test_v2_streams_isolate_faults_from_slip_draws` |
| Faults change neither terrain nor mission layout (v2) | `test_v2_faults_do_not_change_terrain_or_mission_layout` |
| Fault count is Poisson with the configured rate (mean and variance) | `test_fault_counts_follow_the_configured_rate` |
| Ground-relaxation of the hazard threshold lasts one cycle (v2) | `test_v2_intervention_relaxation_lasts_one_cycle` |

## Planner

| Item | Test |
|---|---|
| Fixed and adaptive make identical first decisions (same candidates, routes, risks) | `test_fixed_and_adaptive_face_identical_first_decisions` |
| The fixed planner's belief never moves | `test_fixed_planner_belief_never_moves` |
| Adaptive learning uses the believed class, never the true one | `test_adaptive_update_uses_the_believed_class_not_the_true_one` |
| No planner or belief module can import the terrain generator or true parameters; planners and the mission manager never receive the terrain | `test_planners_and_belief_code_cannot_reach_ground_truth` |
| The risk budget is compared in exactly one place and never violated by a selection | `test_risk_budget_is_enforced_in_exactly_one_place_and_always` |

## Randomness

| Item | Test |
|---|---|
| v2 draws terrain from its own seed and layout, faults, sensing and slip from four separate child streams | `test_v2_draws_from_separate_streams`, `test_v2_sensor_noise_does_not_change_layout_or_fault_schedule`, `test_v2_faults_do_not_change_terrain_or_mission_layout` |
| No planner uses random numbers | `test_no_planner_draws_random_numbers` |

## Study protection

| Item | Test |
|---|---|
| v1 artifacts unchanged since the lock; a sample of committed rows reproduces | `tests/test_v1_lock.py` (all 750: `scripts/verify_v1_reproduction.py`) |
| v2 seed manifest rebuilds from its master seed; all splits disjoint; confirmatory seeds outside every v1 split | `tests/test_v2_protocol.py` |
| Confirmatory terrain cannot be built without a frozen plan and matching authorization; attempts are logged | `test_building_a_confirmatory_terrain_is_refused_and_logged`, `test_authorization_needs_the_frozen_plan_and_its_hash` |
| Development scripts accept only train/validation seeds | `test_calibration_and_power_scripts_accept_only_development_seeds` |

## Documented idealisations (not defects)

- **Slope used by the learner.** Before folding a reading into a class belief, the
  learner removes the slope's contribution using the true slope of the cell driven. This
  stands in for the rover's own attitude sensor measuring the inclination it is standing
  on; the model gives that measurement no noise. It is proprioception, not map knowledge,
  but it is idealised.
- **Class-confusion specification.** The confusion-aware learner (calibration candidate
  M3) uses the classifier's nominal error rate, as a rover would know from pre-flight
  characterisation. Under sensor-degradation faults the true error rate rises and the
  rover does not know it.
- **Spatially independent slip.** Slip draws are independent between cells given the
  cell's class and slope; real terrain has spatial correlation.

## Defects found while building this suite

1. **Reported minimum charge (v1).** The loop could end straight after a draw without
   updating the minimum, so `min_charge` could sit above the final charge. Outcomes are
   unaffected. Fixed in v2; v1 unchanged so its rows reproduce.
2. **Mission layout records outcomes.** `mission_layout` includes each target's final
   visited/abandoned status, so comparing layouts across runs compares outcomes. Not an
   engine defect; tests compare placement and value only.

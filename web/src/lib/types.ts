/**
 * Wire types mirroring src/exonaut/api/models.py.
 *
 * Kept deliberately close to the Python models: the frontend renders values
 * the research engine produced and never computes science of its own, so any
 * shape here should correspond to something the engine already returns.
 */

export type Body = "moon" | "mars";

export interface MissionRequest {
  body: Body;
  planner: string;
  seed: number;
  size: number;
  n_targets: number;
  max_steps: number;
  risk_budget: number;
  fault_rate: number;
  comm_delay: number;
  terrain_uncertainty: number;
  sensor_noise_scale: number;
  sensing_radius: number;
  solar_rate: number;
  energy_reserve_fraction: number;
  prior_body: Body;
  engine: "v1" | "v2";
}

export interface TerrainLayers {
  body: string;
  seed: number;
  size: number;
  gravity: number;
  elevation: number[][];
  slope: number[][];
  roughness: number[][];
  illumination: number[][];
  terrain_class: number[][];
  hazard: boolean[][];
  class_labels: Record<string, string>;
  elevation_range: [number, number];
}

export interface ScienceTarget {
  id: number;
  row: number;
  col: number;
  value: number;
  visited: boolean;
}

export interface CandidateEvaluation {
  target_id: number;
  row: number;
  col: number;
  science_value: number;
  reachable: boolean;
  selected: boolean;
  rejected: string | null;
  path_cells: number | null;
  expected_energy: number | null;
  energy_sd: number | null;
  expected_solar_income: number | null;
  p_failure: number | null;
  p_terrain: number | null;
  p_energy: number | null;
  utility: number | null;
}

export interface TelemetryFrame {
  step: number;
  row: number;
  col: number;
  charge: number;
  charge_fraction: number;
  science: number;
  targets_visited: number;
  slip: number;
  moved: boolean;
  reason: string;
  returning: boolean;
  goal: [number, number] | null;
  planned_path: [number, number][];
  interventions: number;
  predicted_failure_prob: number;
  belief: Record<string, number>;
  belief_sd: Record<string, number>;
  decision_reason: string | null;
  candidates: CandidateEvaluation[];
  decision_index: number;
  sensing_radius: number | null;
}

export interface Provenance {
  run_id: string;
  config_digest: string;
  config: Record<string, number | string | null>;
  git_commit: string | null;
  git_dirty: boolean | null;
  engine_version: string;
  planner: string;
  planner_adaptive: boolean;
  seed: number;
  seed_split: "train" | "validation" | "test" | "ood" | "none";
  seed_quarantined: boolean;
  seed_in_confirmatory_run: boolean;
  executed_utc: string;
}

export interface CandidateRoute extends CandidateEvaluation {
  route: [number, number][];
}

export interface Decision {
  index: number;
  step: number;
  row: number;
  col: number;
  charge_fraction: number;
  reason: string | null;
  risk_budget: number;
  chosen_route: [number, number][];
  candidates: CandidateRoute[];
}

export interface BeliefSnapshot {
  frame_index: number;
  step: number;
  requested_index: number;
  observed: number[][];
  believed_class: number[][];
  expected_slip: number[][];
  slip_sd: number[][];
  risk: number[][];
  hazard_prob: number[][];
  hazard_threshold: number;
  true_slip: number[][];
  true_class: number[][];
}

export interface MissionSummary {
  run_id: string;
  body: string;
  planner: string;
  seed: number;
  termination: string;
  success: boolean;
  science_return: number;
  science_possible: number;
  science_fraction: number;
  targets_visited: number;
  targets_total: number;
  energy_spent: number;
  energy_generated: number;
  final_charge: number;
  min_charge: number;
  steps: number;
  distance_travelled: number;
  interventions: number;
  severe_slip_events: number;
  mean_slip: number;
  planner_replans: number;
  nodes_expanded: number;
  hazard_refusals: number;
  final_distance_from_home: number;
  home: [number, number];
  targets: ScienceTarget[];
  true_class_slip: Record<string, number>;
  n_frames: number;
  n_decisions: number;
  provenance: Provenance | null;
}

export interface MissionStarted {
  session_id: string;
  summary: MissionSummary;
}

export interface PlannerInfo {
  name: string;
  label: string;
  adaptive: boolean;
  description: string;
}

export interface SplitInfo {
  name: string;
  size: number;
  first: number;
  last: number;
  quarantined: number[];
}

export type TerrainLayerName =
  | "surface"
  | "terrain_class"
  | "elevation"
  | "slope"
  | "roughness"
  | "illumination"
  | "hazard"
  | "knowledge"
  | "belief_slip"
  | "true_slip"
  | "slip_error"
  | "risk";

export type CameraMode = "orbit" | "chase" | "top" | "pov" | "planner";

export interface ResultsPayload {
  name: string;
  n_missions: number;
  metadata: Record<string, unknown>;
  descriptive: Record<string, number | string>[];
  primary: Record<string, number | string | boolean>[];
  generalization_gap: Record<string, number | string>[];
  intervals: IntervalRow[];
  paired_points: PairedPoint[];
}

export interface IntervalRow {
  condition: string;
  planner: string;
  n: number;
  successes: number;
  success_rate: number;
  success_ci_low: number;
  success_ci_high: number;
  science_fraction: number;
  science_ci_low: number;
  science_ci_high: number;
}

export interface PairedPoint {
  condition: string;
  seed: number;
  science_treatment: number;
  science_control: number;
  success_treatment: boolean;
  success_control: boolean;
}

export interface FailureRepresentative {
  session_id: string;
  condition: string;
  planner: string;
  seed: number;
  termination: string;
  steps: number;
  science_fraction: number;
  energy_spent: number;
  energy_generated: number;
  min_charge: number;
  final_distance_from_home: number;
  severe_slip_events: number;
  mean_slip: number;
  interventions: number;
  reproduces_committed_row: boolean;
  last_trip: {
    decision_step: number;
    target_id: number;
    expected_round_trip_energy: number | null;
    expected_energy_sd: number | null;
    p_failure: number | null;
    energy_spent_after_decision: number | null;
    mission_ended_step: number | null;
  } | null;
  belief_error_driven_classes: {
    class: number;
    believed: number;
    truth: number;
    error: number;
    n_observations: number;
  }[];
  faults_fired: { step: number; fault: string }[];
}

export interface FailureCategory {
  key: string;
  title: string;
  blurb: string;
  count: number;
  share: number;
  key_measure: string;
  key_label: string;
  distribution: { edges: number[]; counts: number[] } | null;
  median: number | null;
  at_lander: number;
  median_interventions: number | null;
  selection_rule: string;
  representative: FailureRepresentative | null;
}

export interface FailuresPayload {
  planner: string;
  condition: string;
  n_missions: number;
  categories: FailureCategory[];
}

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
  /** reachable and P(failure) <= risk budget, as the engine decided it */
  within_budget: boolean;
  /** 1 = highest utility among within-budget candidates (the one selected) */
  feasible_rank: number | null;
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
  /** grid heading of the last completed move, degrees clockwise from grid north (row 0) */
  heading_deg: number | null;
  local_slope_deg: number | null;
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
  routable: number[][];
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

export type CameraMode = "orbit" | "chase" | "top" | "navcam" | "planner";

export interface ResultsPayload {
  name: string;
  n_missions: number;
  metadata: Record<string, unknown>;
  descriptive: Record<string, number | string>[];
  primary: Record<string, number | string | boolean>[];
  generalization_gap: Record<string, number | string>[];
  secondary: Record<string, number | string | boolean>[];
  intervals: IntervalRow[];
  paired_points: PairedPoint[];
  audit: AuditSummary | null;
}

/** Post-hoc fault-exposure audit (not confirmatory), from data/results. */
export interface AuditSummary {
  Reproduced: number;
  FiredAdaptive: number;
  FiredFixed: number;
  FiredAstar: number;
  MedianSteps: number;
  Horizon: number;
  Discordant: number;
  DiscordantBoth: number;
  DiscordantNone: number;
  DiscordantMixed: number;
}

export type DataStatusName = "GENERATED" | "SIMULATED" | "INFERRED" | "ASSUMED";

export interface ProbeRow {
  key: string;
  label: string;
  value: number | string | boolean | null;
  display: string;
  unit: string;
  status: DataStatusName;
  group: "truth" | "belief";
}

export interface ProbePayload {
  row: number;
  col: number;
  belief_step: number | null;
  belief_frame_index: number | null;
  observed: boolean | null;
  rows: ProbeRow[];
}

export interface ModelConstants {
  max_slope_deg: number;
  severe_slip_threshold: number;
  embed_limit: number;
  hazard_mission_risk: number;
  cell_size_m: number;
}

export interface PairedRun {
  planner: string;
  session_id: string;
  committed: { termination: string; success: boolean; science_fraction: number; energy_spent: number };
  reproduces_committed_row: boolean;
}

export interface PairedReplay {
  condition: string;
  seed: number;
  runs: PairedRun[];
}

export interface DemoMission {
  label: string;
  rule: string;
  caveat: string;
  request: MissionRequest;
  chosen: {
    seed: number;
    termination: string;
    start_frame: number;
    event_frame: number;
    event: {
      target_id: number;
      risk_budget: number;
      /** which risk component alone exceeded the budget */
      crossed_by: ("terrain" | "energy")[];
      belief_class: number;
      belief_before: number;
      belief_after: number;
      decision_before: { index: number; step: number; p_failure: number; p_terrain: number; p_energy: number };
      decision_after: { index: number; step: number; p_failure: number; p_terrain: number; p_energy: number };
    };
  } | null;
  scanned: { seed: number; has_event: boolean }[];
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
    /** (spent − expected) / planner's s.d., computed by the engine */
    energy_error_in_sd: number | null;
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

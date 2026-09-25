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
  | "terrain_class"
  | "elevation"
  | "slope"
  | "roughness"
  | "illumination"
  | "hazard";

export interface ResultsPayload {
  name: string;
  n_missions: number;
  metadata: Record<string, unknown>;
  descriptive: Record<string, number | string>[];
  primary: Record<string, number | string | boolean>[];
  generalization_gap: Record<string, number | string>[];
}

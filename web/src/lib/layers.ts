/**
 * Every map layer the 3D view can show, with its units, range and status.
 *
 * One catalogue drives the colour ramp, the legend, the probe readout and the
 * data-status badge, so the four cannot disagree. Status says where a number
 * comes from, and nothing in this app is a real-world measurement:
 *
 *   GENERATED  procedurally generated terrain (simulator ground truth)
 *   SIMULATED  output of the simulator's physical model (ground truth)
 *   INFERRED   the rover's own belief, computed by its autonomy stack
 *   ASSUMED    a fixed modelling parameter chosen by the author
 */

import type { BeliefSnapshot, TerrainLayerName, TerrainLayers } from "./types";

export type DataStatus = "GENERATED" | "SIMULATED" | "INFERRED" | "ASSUMED";

export const STATUS_STYLE: Record<DataStatus, string> = {
  GENERATED: "border-sky-400/40 text-sky-300",
  SIMULATED: "border-violet-400/40 text-violet-300",
  INFERRED: "border-amber-400/40 text-amber-300",
  ASSUMED: "border-slate-400/40 text-slate-300",
};

export type Ramp = "sequential" | "diverging" | "categorical" | "knowledge";

export interface LayerSpec {
  key: TerrainLayerName;
  label: string;
  group: "surface" | "physical" | "autonomy";
  status: DataStatus;
  unit: string;
  /** legend endpoints, in display units */
  min: number;
  max: number;
  minLabel: string;
  maxLabel: string;
  ramp: Ramp;
  needsBelief: boolean;
  description: string;
  /** value in [0,1] for the colour ramp, or null where undefined */
  normalized: (t: TerrainLayers, b: BeliefSnapshot | null, r: number, c: number) => number | null;
}

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
/** Risk values span 1e-6..1, so they are shown on a log scale. */
const RISK_FLOOR = 1e-5;
export const riskToUnit = (p: number) =>
  clamp01((Math.log10(Math.max(p, RISK_FLOOR)) - Math.log10(RISK_FLOOR)) / -Math.log10(RISK_FLOOR));

export const LAYERS: LayerSpec[] = [
  {
    key: "surface",
    label: "SURFACE",
    group: "surface",
    status: "GENERATED",
    unit: "",
    min: 0,
    max: 1,
    minLabel: "",
    maxLabel: "",
    ramp: "categorical",
    needsBelief: false,
    description:
      "Natural-colour rendering of the simulator's terrain classes. Colour follows terrain class; " +
      "fine surface texture below one grid cell is visual only and carries no data.",
    normalized: () => null,
  },
  {
    key: "terrain_class",
    label: "CLASS",
    group: "physical",
    status: "GENERATED",
    unit: "",
    min: 0,
    max: 4,
    minLabel: "",
    maxLabel: "",
    ramp: "categorical",
    needsBelief: false,
    description: "True terrain class of each cell. The rover only ever sees a noisy guess of this.",
    normalized: () => null,
  },
  {
    key: "elevation",
    label: "ELEVATION",
    group: "physical",
    status: "GENERATED",
    unit: "m",
    min: 0,
    max: 1,
    minLabel: "low",
    maxLabel: "high",
    ramp: "sequential",
    needsBelief: false,
    description: "Height above the lowest point on this map, in model metres (1 grid cell = 1 m).",
    normalized: (t, _b, r, c) => {
      const [lo, hi] = t.elevation_range;
      return (t.elevation[r][c] - lo) / Math.max(hi - lo, 1e-6);
    },
  },
  {
    key: "slope",
    label: "SLOPE",
    group: "physical",
    status: "GENERATED",
    unit: "°",
    min: 0,
    max: 30,
    minLabel: "0°",
    maxLabel: "30°+",
    ramp: "sequential",
    needsBelief: false,
    description: "Ground slope. Cells steeper than 25° are impassable in this model.",
    normalized: (t, _b, r, c) => clamp01(t.slope[r][c] / 30),
  },
  {
    key: "roughness",
    label: "ROUGHNESS",
    group: "physical",
    status: "GENERATED",
    unit: "index",
    min: 0,
    max: 1,
    minLabel: "0.00",
    maxLabel: "1.00",
    ramp: "sequential",
    needsBelief: false,
    description: "Dimensionless surface-roughness index used to assign terrain class. Not a physical unit.",
    normalized: (t, _b, r, c) => clamp01(t.roughness[r][c]),
  },
  {
    key: "illumination",
    label: "LIGHT",
    group: "physical",
    status: "GENERATED",
    unit: "× nominal",
    min: 0,
    max: 1,
    minLabel: "0 (shadow)",
    maxLabel: "1.0 (full sun)",
    ramp: "sequential",
    needsBelief: false,
    description:
      "Fraction of nominal solar flux. The model has no absolute irradiance, so no W/m² is shown; " +
      "solar harvest is this fraction × the assumed harvest rate (Wh per step).",
    normalized: (t, _b, r, c) => clamp01(t.illumination[r][c]),
  },
  {
    key: "knowledge",
    label: "KNOWLEDGE",
    group: "autonomy",
    status: "INFERRED",
    unit: "slip s.d.",
    min: 0,
    max: 0.25,
    minLabel: "certain",
    maxLabel: "uncertain",
    ramp: "knowledge",
    needsBelief: true,
    description:
      "What the rover has seen. Dark cells are unexplored; seen cells are coloured by the rover's " +
      "total uncertainty in their slip.",
    normalized: (_t, b, r, c) => (b ? (b.observed[r][c] ? clamp01(b.slip_sd[r][c] / 0.25) : -1) : null),
  },
  {
    key: "belief_slip",
    label: "BELIEF",
    group: "autonomy",
    status: "INFERRED",
    unit: "slip",
    min: 0,
    max: 1,
    minLabel: "0 (grip)",
    maxLabel: "1 (no progress)",
    ramp: "sequential",
    needsBelief: true,
    description: "Mean wheel slip the rover believes it would experience in each cell. This is what it plans with.",
    normalized: (_t, b, r, c) => (b ? clamp01(b.expected_slip[r][c]) : null),
  },
  {
    key: "true_slip",
    label: "TRUTH",
    group: "autonomy",
    status: "SIMULATED",
    unit: "slip",
    min: 0,
    max: 1,
    minLabel: "0 (grip)",
    maxLabel: "1 (no progress)",
    ramp: "sequential",
    needsBelief: true,
    description: "Simulator ground truth for mean wheel slip. The rover never sees this directly.",
    normalized: (_t, b, r, c) => (b ? clamp01(b.true_slip[r][c]) : null),
  },
  {
    key: "slip_error",
    label: "ERROR",
    group: "autonomy",
    status: "INFERRED",
    unit: "slip",
    min: -0.5,
    max: 0.5,
    minLabel: "−0.5 underestimates",
    maxLabel: "+0.5 overestimates",
    ramp: "diverging",
    needsBelief: true,
    description:
      "Belief minus truth. Blue: the rover thinks the ground is better than it is (the dangerous error). " +
      "Red: worse than it is.",
    normalized: (_t, b, r, c) =>
      b ? clamp01((b.expected_slip[r][c] - b.true_slip[r][c] + 0.5) / 1.0) : null,
  },
  {
    key: "risk",
    label: "RISK",
    group: "autonomy",
    status: "INFERRED",
    unit: "P(fail)",
    min: RISK_FLOOR,
    max: 1,
    minLabel: "≤ 1e-5",
    maxLabel: "1",
    ramp: "sequential",
    needsBelief: true,
    description:
      "The planner's probability that entering the cell ends the mission, log scale. Computed from " +
      "its belief, not from truth.",
    normalized: (_t, b, r, c) => (b ? riskToUnit(b.risk[r][c]) : null),
  },
];

export const LAYER_BY_KEY = Object.fromEntries(LAYERS.map((l) => [l.key, l])) as Record<
  TerrainLayerName,
  LayerSpec
>;

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

import type { BeliefSnapshot, ModelConstants, TerrainLayerName, TerrainLayers } from "./types";

export type DataStatus = "GENERATED" | "SIMULATED" | "INFERRED" | "ASSUMED";

export const STATUS_STYLE: Record<DataStatus, string> = {
  GENERATED: "border-sky-400/40 text-sky-300",
  SIMULATED: "border-violet-400/40 text-violet-300",
  INFERRED: "border-amber-400/40 text-amber-300",
  ASSUMED: "border-slate-400/40 text-slate-300",
};

export type Ramp = "sequential" | "diverging" | "categorical" | "knowledge";

export interface Tick {
  value: number;
  label: string;
}

/** A reference value drawn across the scale, e.g. the slope limit or the risk budget. */
export interface Marker {
  value: number;
  label: string;
}

export interface LegendContext {
  terrain: TerrainLayers;
  constants: ModelConstants | null;
  /** the loaded mission's risk budget ε, from its engine config */
  riskBudget: number | null;
}

export interface LayerSpec {
  key: TerrainLayerName;
  label: string;
  group: "surface" | "physical" | "belief" | "evaluation";
  status: DataStatus;
  unit: string;
  ramp: Ramp;
  needsBelief: boolean;
  description: string;
  /** value in display units at a cell; null where undefined; UNEXPLORED for unseen (knowledge) */
  value: (t: TerrainLayers, b: BeliefSnapshot | null, r: number, c: number) => number | null;
  /** colour-ramp position in [0, 1] for a value. The map and the legend both use this. */
  toUnit: (v: number) => number;
  ticks: (ctx: LegendContext) => Tick[];
  markers?: (ctx: LegendContext) => Marker[];
  /** words under the two ends of the scale */
  ends?: [string, string];
}

export const UNEXPLORED = -1;
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const linear = (lo: number, hi: number) => (v: number) => clamp01((v - lo) / (hi - lo));
const even = (lo: number, hi: number, n: number, digits: number): Tick[] =>
  Array.from({ length: n + 1 }, (_, i) => {
    const v = lo + ((hi - lo) * i) / n;
    return { value: v, label: v.toFixed(digits) };
  });

/** Risk values span 1e-6..1, so they are shown on a log scale. */
const RISK_FLOOR = 1e-5;
export const riskToUnit = (p: number) =>
  clamp01((Math.log10(Math.max(p, RISK_FLOOR)) - Math.log10(RISK_FLOOR)) / -Math.log10(RISK_FLOOR));

const KNOWLEDGE_MAX = 0.25;
const ERROR_SPAN = 0.5;

export const LAYERS: LayerSpec[] = [
  {
    key: "surface",
    label: "SURFACE",
    group: "surface",
    status: "GENERATED",
    unit: "",
    ramp: "categorical",
    needsBelief: false,
    description:
      "Natural-colour rendering of the simulator's terrain classes. Colour follows terrain class; " +
      "fine surface texture below one grid cell is visual only and carries no data.",
    value: () => null,
    toUnit: () => 0,
    ticks: () => [],
  },
  {
    key: "terrain_class",
    label: "CLASS",
    group: "physical",
    status: "GENERATED",
    unit: "",
    ramp: "categorical",
    needsBelief: false,
    description: "True terrain class of each cell. The rover only ever sees a noisy guess of this.",
    value: (t, _b, r, c) => t.terrain_class[r][c],
    toUnit: () => 0,
    ticks: () => [],
  },
  {
    key: "elevation",
    label: "ELEVATION",
    group: "physical",
    status: "GENERATED",
    unit: "m above map minimum",
    ramp: "sequential",
    needsBelief: false,
    description: "Height above the lowest point on this map. One grid cell is one metre across.",
    value: (t, _b, r, c) => t.elevation[r][c] - t.elevation_range[0],
    // the range is per map, so the mapping is built per map in the legend too
    toUnit: (v) => v,
    ticks: ({ terrain }) => {
      const span = terrain.elevation_range[1] - terrain.elevation_range[0];
      return even(0, span, 4, 1);
    },
  },
  {
    key: "slope",
    label: "SLOPE",
    group: "physical",
    status: "GENERATED",
    unit: "°",
    ramp: "sequential",
    needsBelief: false,
    description: "Ground slope. Cells steeper than the model's slope limit (marked) are impassable.",
    value: (t, _b, r, c) => t.slope[r][c],
    toUnit: linear(0, 30),
    ticks: () => even(0, 30, 6, 0),
    markers: ({ constants }) =>
      constants ? [{ value: constants.max_slope_deg, label: `limit ${constants.max_slope_deg}°` }] : [],
  },
  {
    key: "roughness",
    label: "ROUGHNESS",
    group: "physical",
    status: "GENERATED",
    unit: "index",
    ramp: "sequential",
    needsBelief: false,
    description: "Dimensionless surface-roughness index used to assign terrain class. Not a physical unit.",
    value: (t, _b, r, c) => t.roughness[r][c],
    toUnit: linear(0, 1),
    ticks: () => even(0, 1, 4, 2),
  },
  {
    key: "illumination",
    label: "LIGHT",
    group: "physical",
    status: "GENERATED",
    unit: "× nominal flux",
    ramp: "sequential",
    needsBelief: false,
    description:
      "Fraction of nominal solar flux. The model has no absolute irradiance, so no W/m² is shown; " +
      "solar harvest is this fraction × the assumed harvest rate (see the probe).",
    value: (t, _b, r, c) => t.illumination[r][c],
    toUnit: linear(0, 1),
    ticks: () => even(0, 1, 4, 2),
    ends: ["shadow", "full sun"],
  },
  {
    key: "knowledge",
    label: "KNOWLEDGE",
    group: "belief",
    status: "INFERRED",
    unit: "slip s.d.",
    ramp: "knowledge",
    needsBelief: true,
    description:
      "What the rover has seen. Dark cells are unexplored; seen cells are coloured by the rover's " +
      "total uncertainty in their slip.",
    value: (_t, b, r, c) => (b ? (b.observed[r][c] ? b.slip_sd[r][c] : UNEXPLORED) : null),
    toUnit: (v) => (v < 0 ? UNEXPLORED : clamp01(v / KNOWLEDGE_MAX)),
    ticks: () => even(0, KNOWLEDGE_MAX, 5, 2),
    ends: ["certain", "uncertain"],
  },
  {
    key: "belief_slip",
    label: "BELIEF",
    group: "belief",
    status: "INFERRED",
    unit: "mean slip",
    ramp: "sequential",
    needsBelief: true,
    description: "Mean wheel slip the rover believes it would experience in each cell. This is what it plans with.",
    value: (_t, b, r, c) => (b ? b.expected_slip[r][c] : null),
    toUnit: linear(0, 1),
    ticks: () => even(0, 1, 5, 1),
    markers: ({ constants }) =>
      constants ? [{ value: constants.severe_slip_threshold, label: "severe" }] : [],
    ends: ["grip", "no progress"],
  },
  {
    key: "risk",
    label: "RISK",
    group: "belief",
    status: "INFERRED",
    unit: "P(entering ends mission)",
    ramp: "sequential",
    needsBelief: true,
    description:
      "The planner's probability that entering the cell ends the mission, from its belief, not " +
      "from truth. A trip's P(fail) is at least that of its riskiest cell, so no cell right of ε " +
      "can lie on an accepted target trip.",
    value: (_t, b, r, c) => (b ? b.risk[r][c] : null),
    toUnit: riskToUnit,
    ticks: () => [
      { value: 1e-5, label: "≤1e-5" },
      { value: 1e-4, label: "1e-4" },
      { value: 1e-3, label: "1e-3" },
      { value: 1e-2, label: "0.01" },
      { value: 1e-1, label: "0.1" },
      { value: 1, label: "1" },
    ],
    markers: ({ riskBudget }) =>
      riskBudget !== null ? [{ value: riskBudget, label: `ε ${riskBudget.toFixed(2)}` }] : [],
  },
  {
    key: "true_slip",
    label: "TRUTH",
    group: "evaluation",
    status: "SIMULATED",
    unit: "mean slip",
    ramp: "sequential",
    needsBelief: true,
    description: "Simulator ground truth for mean wheel slip. The rover never sees this directly.",
    value: (_t, b, r, c) => (b ? b.true_slip[r][c] : null),
    toUnit: linear(0, 1),
    ticks: () => even(0, 1, 5, 1),
    markers: ({ constants }) =>
      constants ? [{ value: constants.severe_slip_threshold, label: "severe" }] : [],
    ends: ["grip", "no progress"],
  },
  {
    key: "slip_error",
    label: "ERROR",
    group: "evaluation",
    status: "INFERRED",
    unit: "belief − truth, slip",
    ramp: "diverging",
    needsBelief: true,
    description:
      "Belief minus truth, an evaluation the rover cannot make. Blue: it thinks the ground grips " +
      "better than it does (the dangerous error). Red: worse than it does. Values beyond ±0.5 are " +
      "drawn at the ends.",
    value: (_t, b, r, c) => (b ? b.expected_slip[r][c] - b.true_slip[r][c] : null),
    toUnit: (v) => clamp01((v + ERROR_SPAN) / (2 * ERROR_SPAN)),
    ticks: () => [
      { value: -0.5, label: "−0.50" },
      { value: -0.25, label: "−0.25" },
      { value: 0, label: "0" },
      { value: 0.25, label: "+0.25" },
      { value: 0.5, label: "+0.50" },
    ],
    ends: ["underestimates slip", "overestimates slip"],
  },
];

export const LAYER_BY_KEY = Object.fromEntries(LAYERS.map((l) => [l.key, l])) as Record<
  TerrainLayerName,
  LayerSpec
>;

/** Colour-ramp position at a cell, or null where the layer is undefined. */
export function layerUnit(
  spec: LayerSpec,
  t: TerrainLayers,
  b: BeliefSnapshot | null,
  r: number,
  c: number,
): number | null {
  const v = spec.value(t, b, r, c);
  if (v === null) return null;
  if (spec.key === "elevation") {
    const span = Math.max(t.elevation_range[1] - t.elevation_range[0], 1e-6);
    return clamp01(v / span);
  }
  return spec.toUnit(v);
}

/** Legend position of a value, using the same mapping as the map. */
export function legendUnit(spec: LayerSpec, t: TerrainLayers, v: number): number {
  if (spec.key === "elevation") {
    const span = Math.max(t.elevation_range[1] - t.elevation_range[0], 1e-6);
    return clamp01(v / span);
  }
  return spec.toUnit(v);
}

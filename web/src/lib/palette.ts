/**
 * Visual identity: mission control, not gamer HUD.
 *
 * Near-black graphite ground, translucent panels, one restrained orange
 * accent used only for things that need attention. Terrain colouring is
 * scientific rather than decorative - the hazard red is the only saturated
 * colour in the scene, so it reads as a warning rather than as styling.
 */

export const UI = {
  bg: "#07090d",
  panel: "rgba(16,20,28,0.78)",
  panelSolid: "#10141c",
  border: "rgba(148,163,184,0.16)",
  grid: "rgba(148,163,184,0.10)",
  text: "#e8edf5",
  dim: "#93a1b5",
  faint: "#5b6779",
  accent: "#ff7a3d",
  good: "#3ec9a7",
  warn: "#e8c05a",
  bad: "#e8614d",
  route: "#5ad2f2",
  planned: "#9aa8ff",
} as const;

/**
 * Route lines in the 3D view. What lies ahead is bright; what has been driven
 * is subdued, so the decision stays the thing the eye goes to.
 */
export const ROUTE = {
  planned: "#5ad2f2",
  traversed: "#c3ccd8",
  selected: "#3ec9a7",
  feasible: "#a3adbb",
  rejected: "#e8614d",
} as const;

/** Terrain-class colours, keyed by the TerrainClass enum in Python. */
export const CLASS_COLORS: Record<number, [number, number, number]> = {
  0: [0.44, 0.42, 0.40], // smooth regolith
  1: [0.55, 0.52, 0.48], // rocky
  2: [0.79, 0.66, 0.38], // loose fines - the slip trap, deliberately distinct
  3: [0.32, 0.34, 0.38], // bedrock
  4: [0.61, 0.45, 0.34], // rim talus
};

export const CLASS_NAMES: Record<number, string> = {
  0: "smooth regolith",
  1: "rocky",
  2: "loose fines",
  3: "bedrock",
  4: "rim talus",
};

/** Perceptually ordered ramp for scalar layers (dark → bright). */
export function ramp(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t));
  // viridis-like, approximated with a small control-point set
  const stops: [number, [number, number, number]][] = [
    [0.0, [0.19, 0.07, 0.23]],
    [0.25, [0.22, 0.34, 0.55]],
    [0.5, [0.13, 0.57, 0.55]],
    [0.75, [0.37, 0.79, 0.38]],
    [1.0, [0.99, 0.91, 0.14]],
  ];
  for (let i = 0; i < stops.length - 1; i += 1) {
    const [a, ca] = stops[i];
    const [b, cb] = stops[i + 1];
    if (x >= a && x <= b) {
      const u = (x - a) / (b - a);
      return [
        ca[0] + (cb[0] - ca[0]) * u,
        ca[1] + (cb[1] - ca[1]) * u,
        ca[2] + (cb[2] - ca[2]) * u,
      ];
    }
  }
  return stops[stops.length - 1][1];
}

/** Diverging ramp: blue (belief too optimistic) → grey → red (too pessimistic). */
export function diverging(u: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, u));
  const lo: [number, number, number] = [0.2, 0.45, 0.9];
  const mid: [number, number, number] = [0.42, 0.44, 0.47];
  const hi: [number, number, number] = [0.9, 0.32, 0.25];
  const [a, b, f] = x < 0.5 ? [lo, mid, x / 0.5] : [mid, hi, (x - 0.5) / 0.5];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

/** Knowledge ramp: near-black for unexplored (negative), teal (certain) → amber (uncertain). */
export function knowledgeColor(v: number): [number, number, number] {
  if (v < 0) return [0.05, 0.06, 0.08];
  return [0.24 + 0.66 * v, 0.72 - 0.25 * v, 0.66 - 0.5 * v];
}

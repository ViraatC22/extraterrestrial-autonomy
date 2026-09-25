"use client";

/**
 * Plain-SVG research charts. They only lay out numbers the engine computed -
 * intervals, contrasts and counts all arrive from the Python analysis code -
 * so a chart cannot show a statistic the paper does not.
 */

import { useState } from "react";

export const PLANNER_COLOR: Record<string, string> = {
  astar: "#8b98ab",
  risk_aware_astar: "#5ad2f2",
  adaptive_risk_aware_astar: "#ff7a3d",
};
export const PLANNER_SHORT: Record<string, string> = {
  astar: "Distance-only",
  risk_aware_astar: "Fixed risk-aware",
  adaptive_risk_aware_astar: "Adaptive risk-aware",
};

const AXIS = "#3a4656";
const TEXT = "#8b98ab";

function Axis01({ x0, x1, y, ticks = [0, 0.25, 0.5, 0.75, 1] }: { x0: number; x1: number; y: number; ticks?: number[] }) {
  return (
    <g>
      <line x1={x0} x2={x1} y1={y} y2={y} stroke={AXIS} />
      {ticks.map((t) => {
        const x = x0 + (x1 - x0) * t;
        return (
          <g key={t}>
            <line x1={x} x2={x} y1={y} y2={y + 4} stroke={AXIS} />
            <text x={x} y={y + 14} fill={TEXT} fontSize={9} textAnchor="middle" fontFamily="monospace">
              {t.toFixed(2)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

export interface DotRow {
  label: string;
  color: string;
  value: number;
  low: number;
  high: number;
  note?: string;
}

/** One dot per row with its 95% interval, on a 0-1 axis. */
export function DotCIChart({ rows, width = 700 }: { rows: DotRow[]; width?: number }) {
  const left = 140;
  const right = width - 96;
  const rowH = 20;
  const height = rows.length * rowH + 26;
  const sx = (v: number) => left + (right - left) * Math.min(1, Math.max(0, v));
  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img">
      {[0.25, 0.5, 0.75].map((t) => (
        <line key={t} x1={sx(t)} x2={sx(t)} y1={4} y2={rows.length * rowH + 4} stroke="#1c2430" />
      ))}
      {rows.map((r, i) => {
        const y = i * rowH + 14;
        return (
          <g key={r.label}>
            <text x={left - 8} y={y + 3} fill="#c6d0de" fontSize={10} textAnchor="end" fontFamily="monospace">
              {r.label}
            </text>
            <line x1={sx(r.low)} x2={sx(r.high)} y1={y} y2={y} stroke={r.color} strokeWidth={2} opacity={0.75} />
            <line x1={sx(r.low)} x2={sx(r.low)} y1={y - 4} y2={y + 4} stroke={r.color} />
            <line x1={sx(r.high)} x2={sx(r.high)} y1={y - 4} y2={y + 4} stroke={r.color} />
            <circle cx={sx(r.value)} cy={y} r={4.5} fill={r.color} />
            <text x={right + 8} y={y + 3} fill="#e8edf5" fontSize={10} fontFamily="monospace">
              {r.value.toFixed(2)}
              {r.note ? <tspan fill={TEXT}> {r.note}</tspan> : null}
            </text>
          </g>
        );
      })}
      <Axis01 x0={left} x1={right} y={rows.length * rowH + 8} />
    </svg>
  );
}

export interface ForestRow {
  label: string;
  delta: number;
  low: number;
  high: number;
  p: number;
  significant: boolean;
  extra?: string;
}

/** Paired effect with 95% CI; the zero line is "no difference". */
export function ForestPlot({ rows, span = 0.4, width = 700 }: { rows: ForestRow[]; span?: number; width?: number }) {
  const left = 210;
  const right = width - 120;
  const rowH = 22;
  const height = rows.length * rowH + 34;
  const sx = (v: number) => left + ((Math.max(-span, Math.min(span, v)) + span) / (2 * span)) * (right - left);
  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img">
      <line x1={sx(0)} x2={sx(0)} y1={2} y2={rows.length * rowH + 8} stroke="#56657a" strokeDasharray="3 3" />
      {rows.map((r, i) => {
        const y = i * rowH + 14;
        const color = r.significant ? "#3ec9a7" : r.delta >= 0 ? "#9fb3c8" : "#c79a93";
        return (
          <g key={r.label}>
            <text x={left - 8} y={y + 3} fill="#c6d0de" fontSize={10} textAnchor="end" fontFamily="monospace">
              {r.label}
            </text>
            <line x1={sx(r.low)} x2={sx(r.high)} y1={y} y2={y} stroke={color} strokeWidth={2} />
            <rect x={sx(r.delta) - 4} y={y - 4} width={8} height={8} fill={color} />
            <text x={right + 8} y={y + 3} fill={r.significant ? "#3ec9a7" : "#e8edf5"} fontSize={9.5} fontFamily="monospace">
              {r.delta >= 0 ? "+" : ""}
              {r.delta.toFixed(3)} p={r.p < 0.001 ? "<.001" : r.p.toFixed(3)}
              {r.significant ? " ✻" : ""}
            </text>
          </g>
        );
      })}
      <line x1={left} x2={right} y1={rows.length * rowH + 10} y2={rows.length * rowH + 10} stroke={AXIS} />
      {[-span, -span / 2, 0, span / 2, span].map((t) => (
        <text key={t} x={sx(t)} y={rows.length * rowH + 24} fill={TEXT} fontSize={9} textAnchor="middle" fontFamily="monospace">
          {t > 0 ? "+" : ""}
          {t.toFixed(2)}
        </text>
      ))}
      <text x={sx(-span)} y={rows.length * rowH + 33} fill={TEXT} fontSize={8} fontFamily="monospace">
        fixed better
      </text>
      <text x={sx(span)} y={rows.length * rowH + 33} fill={TEXT} fontSize={8} textAnchor="end" fontFamily="monospace">
        adaptive better
      </text>
    </svg>
  );
}

export interface ParetoPoint {
  key: string;
  label: string;
  color: string;
  x: number;
  xLow: number;
  xHigh: number;
  y: number;
  yLow: number;
  yHigh: number;
}

/** Survival (x) against science (y). Up and to the right is better on both. */
export function ParetoPlot({ points, width = 620, height = 360 }: { points: ParetoPoint[]; width?: number; height?: number }) {
  const [hover, setHover] = useState<string | null>(null);
  const m = { l: 44, r: 12, t: 12, b: 36 };
  const sx = (v: number) => m.l + v * (width - m.l - m.r);
  const sy = (v: number) => height - m.b - v * (height - m.t - m.b);
  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img">
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <g key={t}>
          <line x1={sx(t)} x2={sx(t)} y1={sy(0)} y2={sy(1)} stroke="#1c2430" />
          <line x1={sx(0)} x2={sx(1)} y1={sy(t)} y2={sy(t)} stroke="#1c2430" />
          <text x={sx(t)} y={sy(0) + 13} fill={TEXT} fontSize={9} textAnchor="middle" fontFamily="monospace">
            {t.toFixed(2)}
          </text>
          <text x={sx(0) - 6} y={sy(t) + 3} fill={TEXT} fontSize={9} textAnchor="end" fontFamily="monospace">
            {t.toFixed(2)}
          </text>
        </g>
      ))}
      <text x={(sx(0) + sx(1)) / 2} y={height - 4} fill={TEXT} fontSize={9.5} textAnchor="middle" fontFamily="monospace">
        MISSION SUCCESS (returned safely) →
      </text>
      <text
        x={10}
        y={(sy(0) + sy(1)) / 2}
        fill={TEXT}
        fontSize={9.5}
        textAnchor="middle"
        fontFamily="monospace"
        transform={`rotate(-90 10 ${(sy(0) + sy(1)) / 2})`}
      >
        SCIENCE FRACTION →
      </text>
      {points.map((p) => {
        const active = hover === null || hover === p.key;
        return (
          <g
            key={p.key}
            opacity={active ? 1 : 0.25}
            onMouseEnter={() => setHover(p.key)}
            onMouseLeave={() => setHover(null)}
          >
            <line x1={sx(p.xLow)} x2={sx(p.xHigh)} y1={sy(p.y)} y2={sy(p.y)} stroke={p.color} opacity={0.55} />
            <line x1={sx(p.x)} x2={sx(p.x)} y1={sy(p.yLow)} y2={sy(p.yHigh)} stroke={p.color} opacity={0.55} />
            <circle cx={sx(p.x)} cy={sy(p.y)} r={5} fill={p.color} stroke="#07090d" />
            {hover === p.key ? (
              <text x={sx(p.x) + 8} y={sy(p.y) - 8} fill="#e8edf5" fontSize={9.5} fontFamily="monospace">
                {p.label}: success {p.x.toFixed(2)}, science {p.y.toFixed(3)}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

/** One point per matched seed; above the diagonal = adaptive returned more science. */
export function PairedScatter({
  points,
  width = 420,
}: {
  points: { x: number; y: number; both: boolean; onlyT: boolean; onlyC: boolean }[];
  width?: number;
}) {
  const height = width;
  const m = 34;
  const max = Math.max(0.05, ...points.map((p) => Math.max(p.x, p.y)));
  const top = Math.min(1, Math.ceil(max * 10) / 10);
  const sx = (v: number) => m + (v / top) * (width - m - 8);
  const sy = (v: number) => height - m - (v / top) * (height - m - 8);
  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img">
      <line x1={sx(0)} y1={sy(0)} x2={sx(top)} y2={sy(top)} stroke="#56657a" strokeDasharray="3 3" />
      <line x1={sx(0)} x2={sx(top)} y1={sy(0)} y2={sy(0)} stroke={AXIS} />
      <line x1={sx(0)} x2={sx(0)} y1={sy(0)} y2={sy(top)} stroke={AXIS} />
      {[0, top / 2, top].map((t) => (
        <g key={t}>
          <text x={sx(t)} y={sy(0) + 12} fill={TEXT} fontSize={8.5} textAnchor="middle" fontFamily="monospace">
            {t.toFixed(2)}
          </text>
          <text x={sx(0) - 4} y={sy(t) + 3} fill={TEXT} fontSize={8.5} textAnchor="end" fontFamily="monospace">
            {t.toFixed(2)}
          </text>
        </g>
      ))}
      {points.map((p, i) => (
        <circle
          key={i}
          cx={sx(p.x)}
          cy={sy(p.y)}
          r={3.2}
          fill={p.onlyT ? "#ff7a3d" : p.onlyC ? "#5ad2f2" : p.both ? "#3ec9a7" : "#56657a"}
          opacity={0.85}
        />
      ))}
      <text x={(sx(0) + sx(top)) / 2} y={height - 4} fill={TEXT} fontSize={9} textAnchor="middle" fontFamily="monospace">
        FIXED science fraction
      </text>
      <text x={8} y={(sy(0) + sy(top)) / 2} fill={TEXT} fontSize={9} textAnchor="middle" fontFamily="monospace" transform={`rotate(-90 8 ${(sy(0) + sy(top)) / 2})`}>
        ADAPTIVE science fraction
      </text>
    </svg>
  );
}

export interface StackRow {
  label: string;
  parts: { key: string; value: number; color: string }[];
  total: number;
}

/** How missions ended, as a share of each planner's missions. */
export function StackedBars({ rows }: { rows: StackRow[] }) {
  return (
    <div className="space-y-1">
      {rows.map((row) => (
        <div key={row.label} className="flex items-center gap-2">
          <span className="w-[210px] shrink-0 truncate text-right font-mono text-[9.5px] text-slate-400">{row.label}</span>
          <div className="flex h-3 flex-1 overflow-hidden rounded-[1px] bg-white/5">
            {row.parts.map((part) => (
              <div
                key={part.key}
                title={`${part.key}: ${part.value} of ${row.total}`}
                style={{ width: `${(part.value / Math.max(row.total, 1)) * 100}%`, background: part.color }}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/** In-distribution vs out-of-distribution, one line per planner. */
export function SlopeChart({
  rows,
  width = 420,
  height = 280,
}: {
  rows: { planner: string; a: number; b: number }[];
  width?: number;
  height?: number;
}) {
  const xa = 70;
  const xb = width - 70;
  const sy = (v: number) => height - 30 - v * (height - 50);
  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img">
      <line x1={xa} x2={xa} y1={sy(0)} y2={sy(1)} stroke={AXIS} />
      <line x1={xb} x2={xb} y1={sy(0)} y2={sy(1)} stroke={AXIS} />
      <text x={xa} y={height - 12} fill={TEXT} fontSize={9} textAnchor="middle" fontFamily="monospace">
        MOON (ID)
      </text>
      <text x={xb} y={height - 12} fill={TEXT} fontSize={9} textAnchor="middle" fontFamily="monospace">
        MARS (OOD)
      </text>
      {(() => {
        // keep end labels at least 11px apart so close values stay readable
        const place = (key: "a" | "b") => {
          const order = [...rows].sort((p, q) => q[key] - p[key]);
          const ys: Record<string, number> = {};
          let last = -Infinity;
          order.forEach((r) => {
            const y = Math.max(sy(r[key]), last + 11);
            ys[r.planner] = y;
            last = y;
          });
          return ys;
        };
        const la = place("a");
        const lb = place("b");
        return rows.map((r) => (
          <g key={r.planner}>
            <line x1={xa} x2={xb} y1={sy(r.a)} y2={sy(r.b)} stroke={PLANNER_COLOR[r.planner] ?? "#999"} strokeWidth={2} />
            <circle cx={xa} cy={sy(r.a)} r={3.5} fill={PLANNER_COLOR[r.planner]} />
            <circle cx={xb} cy={sy(r.b)} r={3.5} fill={PLANNER_COLOR[r.planner]} />
            <text x={xa - 6} y={la[r.planner] + 3} fill="#e8edf5" fontSize={9} textAnchor="end" fontFamily="monospace">
              {r.a.toFixed(3)}
            </text>
            <text x={xb + 6} y={lb[r.planner] + 3} fill="#e8edf5" fontSize={9} fontFamily="monospace">
              {r.b.toFixed(3)}
            </text>
          </g>
        ));
      })()}
    </svg>
  );
}

export interface SeriesPoint {
  x: number;
  mean: number;
  low: number;
  high: number;
}

/** Outcome against a swept parameter, one line per planner with a 95% band. */
export function SensitivityChart({
  series,
  xLabel,
  yLabel,
  yMax,
  width = 760,
  height = 340,
}: {
  series: { planner: string; points: SeriesPoint[] }[];
  xLabel: string;
  yLabel: string;
  yMax?: number;
  width?: number;
  height?: number;
}) {
  const m = { l: 56, r: 20, t: 14, b: 42 };
  const xs = series.flatMap((s) => s.points.map((p) => p.x));
  if (!xs.length) return null;
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const top =
    yMax ?? Math.max(1e-6, ...series.flatMap((s) => s.points.map((p) => p.high))) * 1.08;
  const sx = (v: number) => m.l + ((v - xMin) / Math.max(xMax - xMin, 1e-9)) * (width - m.l - m.r);
  const sy = (v: number) => height - m.b - (Math.max(0, v) / top) * (height - m.t - m.b);
  const uniqueX = [...new Set(xs)].sort((a, b) => a - b);
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top);
  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img">
      {yTicks.map((t) => (
        <g key={t}>
          <line x1={m.l} x2={width - m.r} y1={sy(t)} y2={sy(t)} stroke="#1c2430" />
          <text x={m.l - 6} y={sy(t) + 3} fill={TEXT} fontSize={9} textAnchor="end" fontFamily="monospace">
            {top <= 1.5 ? t.toFixed(2) : t.toFixed(0)}
          </text>
        </g>
      ))}
      {uniqueX.map((x) => (
        <text key={x} x={sx(x)} y={height - m.b + 14} fill={TEXT} fontSize={9} textAnchor="middle" fontFamily="monospace">
          {x}
        </text>
      ))}
      <text x={(m.l + width - m.r) / 2} y={height - 6} fill={TEXT} fontSize={10} textAnchor="middle" fontFamily="monospace">
        {xLabel}
      </text>
      <text
        x={14}
        y={(m.t + height - m.b) / 2}
        fill={TEXT}
        fontSize={10}
        textAnchor="middle"
        fontFamily="monospace"
        transform={`rotate(-90 14 ${(m.t + height - m.b) / 2})`}
      >
        {yLabel}
      </text>
      {series.map((s) => {
        const pts = [...s.points].sort((a, b) => a.x - b.x);
        const color = PLANNER_COLOR[s.planner] ?? "#999";
        const band =
          pts.map((p) => `${sx(p.x)},${sy(p.high)}`).join(" ") +
          " " +
          [...pts].reverse().map((p) => `${sx(p.x)},${sy(p.low)}`).join(" ");
        return (
          <g key={s.planner}>
            {pts.length > 1 ? <polygon points={band} fill={color} opacity={0.14} /> : null}
            <polyline
              points={pts.map((p) => `${sx(p.x)},${sy(p.mean)}`).join(" ")}
              fill="none"
              stroke={color}
              strokeWidth={2}
            />
            {pts.map((p) => (
              <g key={p.x}>
                <line x1={sx(p.x)} x2={sx(p.x)} y1={sy(p.low)} y2={sy(p.high)} stroke={color} opacity={0.5} />
                <circle cx={sx(p.x)} cy={sy(p.mean)} r={3.5} fill={color}>
                  <title>{`${p.x}: ${p.mean.toFixed(3)} [${p.low.toFixed(3)}, ${p.high.toFixed(3)}]`}</title>
                </circle>
              </g>
            ))}
          </g>
        );
      })}
    </svg>
  );
}

"use client";

/**
 * Controls and readouts laid over the 3D view: layer and camera selection, the
 * legend, the terrain probe, and the provenance record.
 *
 * Every number shown carries a status badge saying where it comes from. Nothing
 * here is a real-world measurement; the badges say which part of the model a
 * value belongs to.
 */

import {
  LAYERS,
  LAYER_BY_KEY,
  STATUS_STYLE,
  legendUnit,
  type DataStatus,
  type LayerSpec,
  type LegendContext,
} from "@/lib/layers";
import { NAVCAM_FOV_DEG } from "@/lib/camera";
import { CLASS_COLORS, CLASS_NAMES, ROUTE, diverging, knowledgeColor, ramp } from "@/lib/palette";
import type {
  CameraMode,
  ModelConstants,
  ProbePayload,
  Provenance,
  TelemetryFrame,
  TerrainLayerName,
  TerrainLayers,
} from "@/lib/types";

const rgb = (c: [number, number, number]) =>
  `rgb(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)})`;

export function StatusBadge({ status }: { status: DataStatus }) {
  return (
    <span
      className={`rounded-sm border px-1 py-[1px] font-mono text-[7.5px] tracking-[0.14em] ${STATUS_STYLE[status]}`}
    >
      {status}
    </span>
  );
}

function ToggleButton({
  active,
  onClick,
  children,
  title,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={`rounded-sm border px-2 py-1 font-mono text-[9px] tracking-[0.16em] transition ${
        active
          ? "border-orange-500/50 bg-orange-500/15 text-orange-300"
          : "border-white/10 bg-black/55 text-slate-400 hover:text-slate-200"
      }`}
    >
      {children}
    </button>
  );
}

export function LayerBar({
  layer,
  onLayer,
  opacity,
  onOpacity,
  hasBelief,
}: {
  layer: TerrainLayerName;
  onLayer: (l: TerrainLayerName) => void;
  opacity: number;
  onOpacity: (o: number) => void;
  hasBelief: boolean;
}) {
  // Belief layers are what the rover plans with; evaluation layers compare
  // that belief with ground truth, which the rover never has.
  const groups: { name: string; hint: string; keys: TerrainLayerName[] }[] = [
    {
      name: "WORLD",
      hint: "simulator ground truth",
      keys: ["surface", "terrain_class", "elevation", "slope", "roughness", "illumination"],
    },
    { name: "ROVER BELIEF", hint: "what the rover plans with", keys: ["knowledge", "belief_slip", "risk"] },
    { name: "EVALUATION", hint: "belief vs truth; the rover cannot see this", keys: ["true_slip", "slip_error"] },
  ];
  return (
    <div className="flex flex-col gap-1">
      {groups.map((group) => (
        <div key={group.name} className="flex flex-wrap items-center gap-1">
          <span className="w-[82px] font-mono text-[8px] tracking-[0.16em] text-slate-500" title={group.hint}>
            {group.name}
          </span>
          {group.keys.map((key) => {
            const spec = LAYER_BY_KEY[key];
            const disabled = spec.needsBelief && !hasBelief;
            return (
              <ToggleButton
                key={key}
                active={layer === key}
                onClick={() => !disabled && onLayer(key)}
                title={disabled ? "launch a mission first" : spec.description}
              >
                <span className={disabled ? "opacity-40" : ""}>{spec.label}</span>
              </ToggleButton>
            );
          })}
        </div>
      ))}
      {layer !== "surface" ? (
        <label className="flex items-center gap-2 pl-[86px]">
          <span className="font-mono text-[8px] tracking-[0.18em] text-slate-500">OPACITY</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={opacity}
            onChange={(e) => onOpacity(Number(e.target.value))}
            className="w-28 accent-orange-500"
          />
          <span className="font-mono text-[9px] tabular-nums text-slate-400">
            {Math.round(opacity * 100)}%
          </span>
        </label>
      ) : null}
    </div>
  );
}

export const CAMERAS: { key: CameraMode; label: string; hint: string }[] = [
  { key: "orbit", label: "ORBIT", hint: "free camera - drag to rotate, scroll to zoom" },
  { key: "chase", label: "CHASE", hint: "spring arm behind the rover; pulls in when terrain or the lander is in the way" },
  { key: "top", label: "TOP DOWN", hint: "plan view of the map" },
  { key: "navcam", label: "NAV CAM", hint: "the rover's mast navigation camera (display view; the simulated sensor is a radius)" },
  { key: "planner", label: "PLANNER", hint: "overview with every candidate route at this decision" },
];

export function CameraBar({
  mode,
  onMode,
  showKeys = false,
}: {
  mode: CameraMode;
  onMode: (m: CameraMode) => void;
  showKeys?: boolean;
}) {
  return (
    <div className="flex gap-1">
      {CAMERAS.map((cam, i) => (
        <ToggleButton key={cam.key} active={mode === cam.key} onClick={() => onMode(cam.key)} title={cam.hint}>
          {showKeys ? <span className="mr-1 text-slate-500">{i + 1}</span> : null}
          {cam.label}
        </ToggleButton>
      ))}
    </div>
  );
}

function rampCss(spec: LayerSpec): string {
  const stops = Array.from({ length: 21 }, (_, i) => i / 20);
  const color = (u: number) =>
    spec.ramp === "diverging" ? diverging(u) : spec.ramp === "knowledge" ? knowledgeColor(u) : ramp(u);
  return `linear-gradient(90deg,${stops.map((u) => rgb(color(u))).join(",")})`;
}

/** Colour bar with ticks and reference markers, positioned by the map's own mapping. */
function ScaleBar({ spec, ctx }: { spec: LayerSpec; ctx: LegendContext }) {
  const ticks = spec.ticks(ctx);
  const markers = spec.markers?.(ctx) ?? [];
  const pct = (v: number) => `${(legendUnit(spec, ctx.terrain, v) * 100).toFixed(2)}%`;
  return (
    <div className={markers.length ? "pt-3.5" : ""}>
      <div className="relative">
        <div className="h-2.5 rounded-[1px]" style={{ background: rampCss(spec) }} />
        {markers.map((m) => (
          <div key={m.label} className="absolute top-[-4px] h-[18px]" style={{ left: pct(m.value) }}>
            <div className="h-full w-[2px] -translate-x-1/2 bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.6)]" />
            <span className="absolute bottom-[19px] -translate-x-1/2 whitespace-nowrap font-mono text-[8px] text-slate-100">
              {m.label}
            </span>
          </div>
        ))}
        <div className="relative h-5">
          {ticks.map((t, i) => {
            const align = i === 0 ? "translate-x-0" : i === ticks.length - 1 ? "-translate-x-full" : "-translate-x-1/2";
            return (
              <div key={t.label} className="absolute top-0" style={{ left: pct(t.value) }}>
                <div className={`h-1 w-px bg-slate-400 ${i === ticks.length - 1 ? "-translate-x-full" : ""}`} />
                <span className={`absolute top-1 whitespace-nowrap font-mono text-[8px] tabular-nums text-slate-400 ${align}`}>
                  {t.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      {spec.ends ? (
        <div className="flex justify-between font-mono text-[8px] text-slate-500">
          <span>{spec.ends[0]}</span>
          {spec.ramp === "diverging" ? <span>correct</span> : null}
          <span>{spec.ends[1]}</span>
        </div>
      ) : null}
    </div>
  );
}

export function Legend({
  layer,
  terrain,
  exaggeration,
  beliefStep,
  constants,
  riskBudget,
}: {
  layer: TerrainLayerName;
  terrain: TerrainLayers;
  exaggeration: number;
  beliefStep: number | null;
  constants: ModelConstants | null;
  riskBudget: number | null;
}) {
  const spec = LAYER_BY_KEY[layer];
  const ctx: LegendContext = { terrain, constants, riskBudget };
  return (
    <div className="w-[290px] rounded-sm border border-white/10 bg-black/65 p-2 backdrop-blur-sm">
      <div className="mb-1 flex items-center justify-between">
        <span className="font-mono text-[10px] tracking-[0.18em] text-slate-200">
          {spec.label}
          {spec.unit ? <span className="ml-1 text-slate-500">[{spec.unit}]</span> : null}
        </span>
        <StatusBadge status={spec.status} />
      </div>

      {spec.ramp === "categorical" ? (
        spec.key === "surface" ? null : (
          <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
            {Object.entries(CLASS_NAMES).map(([k, name]) => (
              <div key={k} className="flex items-center gap-1.5">
                <span className="h-2 w-3 rounded-[1px]" style={{ background: rgb(CLASS_COLORS[Number(k)]) }} />
                <span className="font-mono text-[8.5px] text-slate-400">{name}</span>
              </div>
            ))}
          </div>
        )
      ) : (
        <>
          {spec.ramp === "knowledge" ? (
            <div className="mb-1 flex items-center gap-1.5">
              <span className="h-2.5 w-4 rounded-[1px] border border-white/20 bg-[#0d0f14]" />
              <span className="font-mono text-[8.5px] text-slate-400">unexplored</span>
            </div>
          ) : null}
          <ScaleBar spec={spec} ctx={ctx} />
        </>
      )}

      <p className="mt-1.5 font-mono text-[8.5px] leading-snug text-slate-500">{spec.description}</p>
      {spec.needsBelief && beliefStep !== null ? (
        <p className="mt-1 font-mono text-[8.5px] text-slate-500">belief as of step T+{String(beliefStep).padStart(4, "0")}</p>
      ) : null}
      <div className="mt-1.5 flex flex-wrap gap-x-3 border-t border-white/10 pt-1 font-mono text-[8px] text-slate-500">
        <span>relief ×{exaggeration.toFixed(1)} vertical</span>
        <span>vehicles to scale</span>
        {!spec.needsBelief || spec.key === "true_slip" ? <span>red tint = true hazard</span> : null}
        <span>outside the outline: not simulated</span>
      </div>
    </div>
  );
}

function LineSample({ color, dashed, width, opacity = 1 }: { color: string; dashed?: boolean; width: number; opacity?: number }) {
  return (
    <svg width="26" height="8" aria-hidden>
      <line
        x1="1"
        x2="25"
        y1="4"
        y2="4"
        stroke={color}
        strokeWidth={width}
        strokeDasharray={dashed ? "5 3" : undefined}
        opacity={opacity}
      />
    </svg>
  );
}

/** Key to the route lines drawn in the 3D view. */
export function RouteLegend({ planner, riskBudget }: { planner: boolean; riskBudget: number | null }) {
  const rows: [React.ReactNode, string][] = planner
    ? [
        [<LineSample key="s" color={ROUTE.selected} width={3} />, "selected route"],
        [<LineSample key="f" color={ROUTE.feasible} width={1.5} dashed />, "feasible alternative"],
        [
          <LineSample key="r" color={ROUTE.rejected} width={1.5} dashed />,
          `rejected: P(fail) > ε${riskBudget !== null ? ` ${riskBudget.toFixed(2)}` : ""}`,
        ],
        [<LineSample key="t" color={ROUTE.traversed} width={2} opacity={0.6} />, "traversed"],
      ]
    : [
        [<LineSample key="p" color={ROUTE.planned} width={2.6} />, "planned route (ahead)"],
        [<LineSample key="t" color={ROUTE.traversed} width={2} opacity={0.6} />, "traversed"],
      ];
  return (
    <div className="rounded-sm border border-white/10 bg-black/60 px-2 py-1 backdrop-blur-sm">
      {rows.map(([sample, label]) => (
        <div key={label} className="flex items-center gap-1.5 font-mono text-[8.5px] text-slate-300">
          {sample}
          {label}
        </div>
      ))}
    </div>
  );
}

/** Minimal instrument readout for the navigation-camera view. */
export function NavcamReadout({ frame }: { frame: TelemetryFrame | null }) {
  const rows: [string, string, DataStatus | null][] = [
    ["FOV", `${NAVCAM_FOV_DEG}° display`, null],
    [
      "HEADING",
      frame?.heading_deg !== null && frame?.heading_deg !== undefined
        ? `${String(Math.round(frame.heading_deg)).padStart(3, "0")}° grid`
        : "—",
      "SIMULATED",
    ],
    ["SENSING", frame?.sensing_radius ? `${frame.sensing_radius} cells, all round` : "—", "SIMULATED"],
    [
      "LOCAL SLOPE",
      frame?.local_slope_deg !== null && frame?.local_slope_deg !== undefined
        ? `${frame.local_slope_deg.toFixed(1)}°`
        : "—",
      "GENERATED",
    ],
  ];
  return (
    <div className="pointer-events-none rounded-sm bg-black/35 px-2 py-1.5 font-mono text-[9px] text-slate-300">
      <div className="mb-1 tracking-[0.2em] text-slate-100">NAVCAM // ROVER-01</div>
      {rows.map(([label, value, status]) => (
        <div key={label} className="flex items-center justify-between gap-4">
          <span className="tracking-[0.14em] text-slate-500">{label}</span>
          <span className="flex items-center gap-1 tabular-nums">
            {value}
            {status ? <StatusBadge status={status} /> : null}
          </span>
        </div>
      ))}
      <div className="mt-1 max-w-[210px] text-[7.5px] leading-snug text-slate-500">
        Rendered camera view. The simulated sensor is a radius around the rover, not this frustum.
      </div>
    </div>
  );
}

export interface ProbeColumn {
  tag: string;
  data: ProbePayload;
}

/** Terrain probe: one column for the hovered cell, or two pinned cells side by side. */
export function ProbePanel({
  columns,
  pinned,
  onClear,
}: {
  columns: ProbeColumn[];
  pinned: boolean;
  onClear: () => void;
}) {
  if (!columns.length) return null;
  const first = columns[0].data;
  const byKey = columns.map((col) => Object.fromEntries(col.data.rows.map((r) => [r.key, r])));
  const beliefStep = columns.find((c) => c.data.belief_step !== null)?.data.belief_step ?? null;
  const section = (group: "truth" | "belief") =>
    first.rows
      .filter((row) => row.group === group)
      .map((row) => (
        <tr key={row.key} className="border-t border-white/[0.04]">
          <td className="py-[2px] pr-2 font-mono text-[8.5px] leading-tight tracking-[0.08em] text-slate-500">
            {row.label}
            {row.unit ? <span className="ml-1 text-[7.5px] tracking-normal text-slate-600">{row.unit}</span> : null}
          </td>
          {byKey.map((values, i) => (
            <td key={i} className="py-[2px] pr-2 text-right font-mono text-[10.5px] tabular-nums text-slate-100">
              {values[row.key]?.display ?? "—"}
            </td>
          ))}
          <td className="py-[2px] text-right">
            <StatusBadge status={row.status} />
          </td>
        </tr>
      ));
  return (
    <div className="max-w-[400px] rounded-sm border border-white/15 bg-black/80 p-2 backdrop-blur-sm">
      <div className="mb-1 flex items-center justify-between gap-3 font-mono text-[10px] tracking-[0.18em] text-slate-200">
        <span>{pinned ? "TERRAIN PROBE · COMPARE" : "TERRAIN PROBE"}</span>
        {pinned ? (
          <button
            onClick={onClear}
            className="pointer-events-auto rounded-sm border border-white/15 px-1.5 font-mono text-[8px] tracking-[0.16em] text-slate-400 hover:text-slate-200"
          >
            CLEAR PINS
          </button>
        ) : (
          <span className="text-[8px] tracking-[0.1em] text-slate-500">click to pin · pin two to compare</span>
        )}
      </div>
      <table className="w-full">
        <thead>
          <tr>
            <th />
            {columns.map((col) => (
              <th key={col.tag} className="pr-2 text-right font-mono text-[9px] font-normal tracking-[0.12em] text-slate-300">
                {col.tag} <span className="text-slate-500">({col.data.row}, {col.data.col})</span>
              </th>
            ))}
            <th />
          </tr>
        </thead>
        <tbody>
          <tr>
            <td colSpan={columns.length + 2} className="pt-1 font-mono text-[8px] text-slate-500">
              simulator ground truth
            </td>
          </tr>
          {section("truth")}
          {beliefStep !== null ? (
            <>
              <tr>
                <td colSpan={columns.length + 2} className="pt-1.5 font-mono text-[8px] text-slate-500">
                  rover belief at T+{String(beliefStep).padStart(4, "0")}
                </td>
              </tr>
              <tr className="border-t border-white/[0.04]">
                <td className="py-[2px] pr-2 font-mono text-[8.5px] tracking-[0.08em] text-slate-500">SEEN BY ROVER</td>
                {columns.map((col) => (
                  <td key={col.tag} className="py-[2px] pr-2 text-right font-mono text-[10.5px] text-slate-100">
                    {col.data.observed ? "yes" : "no"}
                  </td>
                ))}
                <td className="text-right">
                  <StatusBadge status="INFERRED" />
                </td>
              </tr>
              {section("belief")}
            </>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

const SPLIT_TONE: Record<string, string> = {
  train: "text-slate-300",
  validation: "text-emerald-300",
  test: "text-amber-300",
  ood: "text-amber-300",
  none: "text-slate-400",
};

export function ProvenancePanel({ provenance }: { provenance: Provenance }) {
  const heldOut =
    (provenance.seed_split === "test" || provenance.seed_split === "ood") &&
    !provenance.seed_in_confirmatory_run;
  const rows: [string, string][] = [
    ["RUN ID", provenance.run_id],
    ["CONFIG DIGEST", provenance.config_digest],
    ["GIT COMMIT", `${provenance.git_commit?.slice(0, 10) ?? "unknown"}${provenance.git_dirty ? " (dirty)" : ""}`],
    ["ENGINE", `v${provenance.engine_version} · profile ${String(provenance.config.engine ?? "v1")}`],
    ["PLANNER", `${provenance.planner}${provenance.planner_adaptive ? " (adaptive)" : ""}`],
    ["SEED", String(provenance.seed)],
    ["EXECUTED", provenance.executed_utc.replace("T", " ").replace("+00:00", " UTC")],
  ];
  return (
    <div className="space-y-0.5">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between gap-2">
          <span className="font-mono text-[8.5px] tracking-[0.12em] text-slate-500">{label}</span>
          <span className="truncate font-mono text-[9.5px] text-slate-200" title={value}>
            {value}
          </span>
        </div>
      ))}
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-[8.5px] tracking-[0.12em] text-slate-500">SEED SPLIT</span>
        <span className={`font-mono text-[9.5px] uppercase ${SPLIT_TONE[provenance.seed_split]}`}>
          {provenance.seed_split}
          {provenance.seed_quarantined ? " · quarantined" : ""}
        </span>
      </div>
      {provenance.seed_in_confirmatory_run ? (
        <p className="mt-1 rounded-sm border border-sky-400/30 bg-sky-400/10 p-1.5 font-mono text-[8.5px] leading-snug text-sky-200">
          Replay of a mission from the completed confirmatory run. The engine is deterministic,
          so this reproduces the committed result.
        </p>
      ) : null}
      {heldOut ? (
        <p className="mt-1 rounded-sm border border-amber-400/30 bg-amber-400/10 p-1.5 font-mono text-[8.5px] leading-snug text-amber-200">
          Held-out seed. Viewing it cannot change any committed result, but this terrain has now
          been seen - use validation seeds for exploration.
        </p>
      ) : null}
    </div>
  );
}

export { LAYERS };

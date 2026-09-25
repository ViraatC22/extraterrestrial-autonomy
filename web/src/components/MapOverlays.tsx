"use client";

/**
 * Controls and readouts laid over the 3D view: layer and camera selection, the
 * legend, the terrain probe, and the provenance record.
 *
 * Every number shown carries a status badge saying where it comes from. Nothing
 * here is a real-world measurement; the badges say which part of the model a
 * value belongs to.
 */

import { LAYERS, LAYER_BY_KEY, STATUS_STYLE, type DataStatus } from "@/lib/layers";
import { CLASS_COLORS, CLASS_NAMES, ramp } from "@/lib/palette";
import type {
  BeliefSnapshot,
  CameraMode,
  MissionRequest,
  Provenance,
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
  const groups: { name: string; keys: TerrainLayerName[] }[] = [
    { name: "WORLD", keys: ["surface", "terrain_class", "elevation", "slope", "roughness", "illumination"] },
    { name: "ROVER KNOWS", keys: ["knowledge", "belief_slip", "true_slip", "slip_error", "risk"] },
  ];
  return (
    <div className="flex flex-col gap-1">
      {groups.map((group) => (
        <div key={group.name} className="flex flex-wrap items-center gap-1">
          <span className="w-[74px] font-mono text-[8px] tracking-[0.18em] text-slate-500">{group.name}</span>
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
        <label className="flex items-center gap-2 pl-[78px]">
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

const CAMERAS: { key: CameraMode; label: string; hint: string }[] = [
  { key: "orbit", label: "ORBIT", hint: "free camera - drag to rotate, scroll to zoom" },
  { key: "chase", label: "CHASE", hint: "follow the rover from behind" },
  { key: "top", label: "TOP DOWN", hint: "plan view of the map" },
  { key: "pov", label: "ROVER POV", hint: "approximate mast-camera view" },
  { key: "planner", label: "PLANNER", hint: "overview with every candidate route at this decision" },
];

export function CameraBar({ mode, onMode }: { mode: CameraMode; onMode: (m: CameraMode) => void }) {
  return (
    <div className="flex gap-1">
      {CAMERAS.map((cam) => (
        <ToggleButton key={cam.key} active={mode === cam.key} onClick={() => onMode(cam.key)} title={cam.hint}>
          {cam.label}
        </ToggleButton>
      ))}
    </div>
  );
}

export function Legend({
  layer,
  terrain,
  exaggeration,
  beliefStep,
}: {
  layer: TerrainLayerName;
  terrain: TerrainLayers;
  exaggeration: number;
  beliefStep: number | null;
}) {
  const spec = LAYER_BY_KEY[layer];
  const stops = Array.from({ length: 11 }, (_, i) => i / 10);
  let gradient = "";
  if (spec.ramp === "sequential") gradient = stops.map((s) => rgb(ramp(s))).join(",");
  if (spec.ramp === "diverging") gradient = "rgb(51,115,230),rgb(107,112,120),rgb(230,82,64)";
  if (spec.ramp === "knowledge") gradient = "rgb(61,184,168),rgb(230,120,40)";
  return (
    <div className="w-[270px] rounded-sm border border-white/10 bg-black/65 p-2 backdrop-blur-sm">
      <div className="mb-1 flex items-center justify-between">
        <span className="font-mono text-[10px] tracking-[0.18em] text-slate-200">
          {spec.label}
          {spec.unit ? <span className="ml-1 text-slate-500">[{spec.unit}]</span> : null}
        </span>
        <StatusBadge status={spec.status} />
      </div>

      {gradient ? (
        <>
          {spec.ramp === "knowledge" ? (
            <div className="mb-1 flex items-center gap-1.5">
              <span className="h-2.5 w-4 rounded-[1px] border border-white/20 bg-[#0d0f14]" />
              <span className="font-mono text-[8.5px] text-slate-400">unexplored</span>
            </div>
          ) : null}
          <div className="h-2.5 rounded-[1px]" style={{ background: `linear-gradient(90deg,${gradient})` }} />
          <div className="mt-0.5 flex justify-between font-mono text-[8.5px] text-slate-400">
            <span>{spec.key === "elevation" ? `${terrain.elevation_range[0].toFixed(1)} m` : spec.minLabel}</span>
            <span>{spec.key === "elevation" ? `${terrain.elevation_range[1].toFixed(1)} m` : spec.maxLabel}</span>
          </div>
        </>
      ) : (
        <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
          {Object.entries(CLASS_NAMES).map(([k, name]) => (
            <div key={k} className="flex items-center gap-1.5">
              <span
                className="h-2 w-3 rounded-[1px]"
                style={{ background: rgb(CLASS_COLORS[Number(k)]) }}
              />
              <span className="font-mono text-[8.5px] text-slate-400">{name}</span>
            </div>
          ))}
        </div>
      )}

      <p className="mt-1.5 font-mono text-[8.5px] leading-snug text-slate-500">{spec.description}</p>
      {spec.needsBelief && beliefStep !== null ? (
        <p className="mt-1 font-mono text-[8.5px] text-slate-500">belief as of step T+{String(beliefStep).padStart(4, "0")}</p>
      ) : null}
      <div className="mt-1.5 flex flex-wrap gap-x-3 border-t border-white/10 pt-1 font-mono text-[8px] text-slate-500">
        <span>vertical exaggeration ×{exaggeration.toFixed(1)}</span>
        {!spec.needsBelief || spec.key === "true_slip" ? <span>red tint = true hazard</span> : null}
        <span>outside the outline: not simulated</span>
      </div>
    </div>
  );
}

function ProbeRow({
  label,
  value,
  status,
}: {
  label: string;
  value: string;
  status: DataStatus;
}) {
  return (
    <div className="flex items-center justify-between gap-2 py-[1.5px]">
      <span className="font-mono text-[9px] tracking-[0.1em] text-slate-500">{label}</span>
      <span className="flex items-center gap-1.5">
        <span className="font-mono text-[11px] tabular-nums text-slate-100">{value}</span>
        <StatusBadge status={status} />
      </span>
    </div>
  );
}

export function ProbePanel({
  terrain,
  belief,
  cell,
  request,
}: {
  terrain: TerrainLayers;
  belief: BeliefSnapshot | null;
  cell: [number, number];
  request: MissionRequest;
}) {
  const [r, c] = cell;
  const illum = terrain.illumination[r][c];
  const seen = belief ? Boolean(belief.observed[r][c]) : false;
  const hazardBelief = belief?.hazard_prob[r][c];
  return (
    <div className="w-[270px] rounded-sm border border-white/15 bg-black/75 p-2 backdrop-blur-sm">
      <div className="mb-1 flex justify-between font-mono text-[10px] tracking-[0.18em] text-slate-200">
        <span>TERRAIN PROBE</span>
        <span className="text-slate-400">
          GRID {r}, {c}
        </span>
      </div>
      <p className="mb-1 font-mono text-[8px] text-slate-500">simulator ground truth</p>
      <ProbeRow
        label="ELEVATION"
        value={`${(terrain.elevation[r][c] - terrain.elevation_range[0]).toFixed(2)} m`}
        status="GENERATED"
      />
      <ProbeRow label="SLOPE" value={`${terrain.slope[r][c].toFixed(1)}°`} status="GENERATED" />
      <ProbeRow label="ROUGHNESS" value={terrain.roughness[r][c].toFixed(2)} status="GENERATED" />
      <ProbeRow label="CLASS" value={CLASS_NAMES[terrain.terrain_class[r][c]]} status="GENERATED" />
      <ProbeRow label="HAZARD" value={terrain.hazard[r][c] ? "IMPASSABLE" : "passable"} status="GENERATED" />
      <ProbeRow label="ILLUMINATION" value={`${illum.toFixed(2)} × nominal`} status="GENERATED" />
      <ProbeRow
        label="SOLAR HARVEST"
        value={`${(illum * request.solar_rate).toFixed(2)} Wh/step`}
        status="ASSUMED"
      />
      {belief ? (
        <>
          <ProbeRow label="TRUE MEAN SLIP" value={belief.true_slip[r][c].toFixed(3)} status="SIMULATED" />
          <p className="mb-1 mt-1.5 border-t border-white/10 pt-1 font-mono text-[8px] text-slate-500">
            rover belief at T+{String(belief.step).padStart(4, "0")} {seen ? "· cell observed" : "· never observed"}
          </p>
          <ProbeRow
            label="BELIEVED CLASS"
            value={seen ? CLASS_NAMES[belief.believed_class[r][c]] : "unknown"}
            status="INFERRED"
          />
          <ProbeRow
            label="BELIEVED SLIP"
            value={`${belief.expected_slip[r][c].toFixed(3)} ± ${belief.slip_sd[r][c].toFixed(3)}`}
            status="INFERRED"
          />
          <ProbeRow
            label="P(HAZARD)"
            value={hazardBelief !== undefined ? hazardBelief.toFixed(2) : "—"}
            status="INFERRED"
          />
          <ProbeRow
            label="ROUTABLE"
            value={
              hazardBelief !== undefined && hazardBelief < belief.hazard_threshold ? "yes" : "no"
            }
            status="INFERRED"
          />
          <ProbeRow
            label="P(ENTRY ENDS MISSION)"
            value={belief.risk[r][c] < 1e-5 ? "< 1e-5" : belief.risk[r][c].toExponential(1)}
            status="INFERRED"
          />
          <ProbeRow
            label="P(SAFE ENTRY)"
            value={(1 - belief.risk[r][c]).toFixed(5)}
            status="INFERRED"
          />
        </>
      ) : null}
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
  const heldOut = provenance.seed_split === "test" || provenance.seed_split === "ood";
  const rows: [string, string][] = [
    ["RUN ID", provenance.run_id],
    ["CONFIG DIGEST", provenance.config_digest],
    ["GIT COMMIT", `${provenance.git_commit?.slice(0, 10) ?? "unknown"}${provenance.git_dirty ? " (dirty)" : ""}`],
    ["ENGINE", `v${provenance.engine_version}`],
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

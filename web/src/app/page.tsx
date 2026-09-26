"use client";

/**
 * MISSION CONTROL — the demo surface.
 *
 * Everything shown here is produced by the Python engine and delivered over
 * the API. The page holds no simulation logic; it schedules playback and
 * draws state. Deep links:
 *
 *   /?session=<id>&frame=<n>&camera=<mode>   a mission the engine already ran
 *   /?paired=<condition>:<seed>              a confirmatory seed, both planners
 *   /?demo=1                                 the rule-selected demonstration mission
 */

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { verticalExaggeration } from "@/components/TerrainMesh";
import {
  CameraBar,
  LayerBar,
  Legend,
  NavcamReadout,
  ProbePanel,
  ProvenancePanel,
  RouteLegend,
  StatusBadge,
  type ProbeColumn,
} from "@/components/MapOverlays";
import { Nav } from "@/components/Nav";
import { ReplayLog, Timeline } from "@/components/Timeline";
import {
  AutonomyPanel,
  BeliefPanel,
  MissionHeader,
  Panel,
  Readout,
  RoverStatus,
} from "@/components/Panels";
import {
  DEFAULT_MISSION,
  getBelief,
  getDecisions,
  getDemoMission,
  getModelConstants,
  getPairedReplay,
  getPlanners,
  getProbe,
  getSplits,
  getSummary,
  getTerrain,
  startMission,
  getTelemetry,
  ApiError,
} from "@/lib/api";
import { LAYERS, LAYER_BY_KEY } from "@/lib/layers";
import { CLASS_NAMES } from "@/lib/palette";
import { buildReplayEvents, latestEvent } from "@/lib/replay";
import type {
  BeliefSnapshot,
  CameraMode,
  Decision,
  DemoMission,
  MissionRequest,
  MissionSummary,
  ModelConstants,
  PairedReplay,
  PlannerInfo,
  ProbePayload,
  SplitInfo,
  TelemetryFrame,
  TerrainLayers,
  TerrainLayerName,
} from "@/lib/types";

// three.js cannot render on the server.
const MissionScene = dynamic(
  () => import("@/components/MissionScene").then((m) => m.MissionScene),
  { ssr: false, loading: () => <SceneFallback label="initialising 3D world…" /> },
);

function SceneFallback({ label }: { label: string }) {
  return (
    <div className="flex h-full w-full items-center justify-center bg-[#07090d]">
      <p className="font-mono text-[11px] tracking-[0.2em] text-slate-500">{label}</p>
    </div>
  );
}

const CAMERA_ORDER: CameraMode[] = ["orbit", "chase", "top", "navcam", "planner"];
const PAIRED_LABEL: Record<string, string> = {
  risk_aware_astar: "FIXED",
  adaptive_risk_aware_astar: "ADAPTIVE",
};
const CONDITION_LABEL: Record<string, string> = {
  moon_id: "Moon (in-distribution)",
  mars_ood: "Mars (out-of-distribution)",
  mars_high_uncertainty: "Mars · 1.5× slip dispersion",
  mars_faults: "Mars · faults scheduled",
  mars_comm_delay: "Mars · 20-step comm delay",
};

const clampIndex = (i: number, n: number) => Math.min(Math.max(0, Number.isFinite(i) ? i : 0), Math.max(n - 1, 0));
const outcomeText = (termination: string, success: boolean) =>
  success ? "returned safely" : termination.replace("_", " ");

/**
 * Engine probe for one cell at a frame. One request in flight at a time;
 * when it lands, if the cell or frame has moved on, it fetches again - so it
 * keeps up with the pointer and with playback without a request per event.
 */
function useProbe(sessionId: string | null, row: number | null, col: number | null, index: number) {
  const [data, setData] = useState<ProbePayload | null>(null);
  const wanted = useRef<{ sid: string; row: number; col: number; index: number } | null>(null);
  const inFlight = useRef(false);
  const pull = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      for (;;) {
        const w = wanted.current;
        if (!w) return;
        const payload = await getProbe(w.sid, w.row, w.col, w.index);
        if (wanted.current === null) return;
        if (wanted.current === w) {
          setData(payload);
          return;
        }
      }
    } catch {
      /* the probe decorates the view; the mission plays without it */
    } finally {
      inFlight.current = false;
    }
  }, []);
  useEffect(() => {
    wanted.current = sessionId !== null && row !== null && col !== null ? { sid: sessionId, row, col, index } : null;
    void pull();
  }, [sessionId, row, col, index, pull]);
  return row !== null && col !== null && data && data.row === row && data.col === col ? data : null;
}

/** Vertical tab shown in place of a collapsed side column. */
function Rail({ label, side, onOpen }: { label: string; side: "left" | "right"; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      title={`show ${label.toLowerCase()}`}
      className="hidden h-full w-full items-start justify-center rounded-sm border border-white/10 bg-[#10141c]/80 pt-3 hover:bg-white/5 lg:flex"
    >
      <span className="font-mono text-[9px] tracking-[0.22em] text-slate-400 [writing-mode:vertical-rl]">
        {side === "left" ? "› " : "‹ "}
        {label}
      </span>
    </button>
  );
}

function DemoBanner({ demo, summary }: { demo: DemoMission; summary: MissionSummary | null }) {
  const [open, setOpen] = useState(false);
  const chosen = demo.chosen;
  if (!chosen) return null;
  const e = chosen.event;
  const truth = summary?.true_class_slip[String(e.belief_class)];
  return (
    <div className="rounded-sm border border-sky-400/30 bg-sky-400/[0.07] px-3 py-1.5 font-mono text-[9.5px] leading-relaxed text-sky-100">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>
          <span className="mr-2 tracking-[0.2em] text-sky-300">{demo.label}</span>
          validation seed {chosen.seed}, chosen by a written rule — not evidence of how often adaptation helps
        </span>
        <button onClick={() => setOpen((o) => !o)} className="tracking-[0.16em] text-sky-300 hover:text-sky-100">
          {open ? "HIDE RULE" : "SELECTION RULE"}
        </button>
      </div>
      <div className="text-slate-200">
        At T+{String(e.decision_after.step).padStart(4, "0")} target TGT {String(e.target_id).padStart(2, "0")} was
        rejected: P(fail) {e.decision_before.p_failure.toFixed(3)} → {e.decision_after.p_failure.toFixed(3)} against
        ε {e.risk_budget.toFixed(2)} ({e.crossed_by.join(" and ")} risk), after the rover revised its{" "}
        {CLASS_NAMES[e.belief_class]} slip belief {e.belief_before.toFixed(2)} → {e.belief_after.toFixed(2)}
        {truth !== undefined ? ` (true mean ${truth.toFixed(2)})` : ""}.
      </div>
      {open ? (
        <p className="mt-1 border-t border-sky-400/20 pt-1 text-[9px] text-slate-300">
          {demo.rule} {demo.caveat} Seeds scanned: {demo.scanned.length}.
        </p>
      ) : null}
    </div>
  );
}

function PairedBar({
  paired,
  active,
  onSelect,
}: {
  paired: PairedReplay;
  active: number;
  onSelect: (i: number) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-sm border border-white/10 bg-black/40 px-3 py-1.5 font-mono text-[9.5px]">
      <span className="tracking-[0.18em] text-slate-300">PAIRED REPLAY</span>
      <span className="text-slate-400">
        confirmatory seed {paired.seed} · {CONDITION_LABEL[paired.condition] ?? paired.condition} · same terrain, same
        seed
      </span>
      <span className="ml-auto flex gap-1">
        {paired.runs.map((run, i) => (
          <button
            key={run.planner}
            onClick={() => onSelect(i)}
            className={`rounded-sm border px-2 py-0.5 tracking-[0.12em] ${
              i === active
                ? "border-orange-500/50 bg-orange-500/15 text-orange-200"
                : "border-white/10 text-slate-400 hover:text-slate-200"
            }`}
            title={
              run.reproduces_committed_row
                ? "re-run reproduces its committed row exactly"
                : "WARNING: re-run does not reproduce its committed row"
            }
          >
            {PAIRED_LABEL[run.planner] ?? run.planner}:{" "}
            <span className={run.committed.success ? "text-emerald-300" : "text-rose-300"}>
              {outcomeText(run.committed.termination, run.committed.success)}
            </span>
            <span className={run.reproduces_committed_row ? "text-slate-500" : "text-rose-400"}>
              {run.reproduces_committed_row ? " ✓" : " ✕"}
            </span>
          </button>
        ))}
      </span>
    </div>
  );
}

export default function MissionControl() {
  const [planners, setPlanners] = useState<PlannerInfo[]>([]);
  const [splits, setSplits] = useState<SplitInfo[]>([]);
  const [constants, setConstants] = useState<ModelConstants | null>(null);
  const [request, setRequest] = useState<MissionRequest>(DEFAULT_MISSION);
  const [terrain, setTerrain] = useState<TerrainLayers | null>(null);
  const [summary, setSummary] = useState<MissionSummary | null>(null);
  const [frames, setFrames] = useState<TelemetryFrame[]>([]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(90);
  const [layer, setLayer] = useState<TerrainLayerName>("surface");
  const [opacity, setOpacity] = useState(0.85);
  const [cameraMode, setCameraMode] = useState<CameraMode>("orbit");
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [belief, setBelief] = useState<BeliefSnapshot | null>(null);
  const [hoverCell, setHoverCell] = useState<[number, number] | null>(null);
  const [pins, setPins] = useState<[number, number][]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [paired, setPaired] = useState<PairedReplay | null>(null);
  const [pairedActive, setPairedActive] = useState(1);
  const [demo, setDemo] = useState<DemoMission | null>(null);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [presenting, setPresenting] = useState(false);

  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const terrainCache = useRef<TerrainLayers | null>(null);

  useEffect(() => {
    getPlanners().then(setPlanners).catch(() => undefined);
    getSplits().then(setSplits).catch(() => undefined);
    getModelConstants().then(setConstants).catch(() => undefined);
  }, []);

  /** Show a mission the engine has already run. Returns its frame count. */
  const loadSession = useCallback(
    async (id: string, opts: { frame?: number; camera?: CameraMode; keepFrame?: boolean } = {}) => {
      const loaded = await getSummary(id);
      const config = (loaded.provenance?.config ?? {}) as Partial<MissionRequest>;
      const body = (config.body ?? loaded.body) as MissionRequest["body"];
      const size = Number(config.size ?? 56);
      const cached = terrainCache.current;
      const sameTerrain = cached && cached.body === body && cached.seed === loaded.seed && cached.size === size;
      const [layers, telemetry, decisionList] = await Promise.all([
        sameTerrain ? Promise.resolve(cached) : getTerrain(body, loaded.seed, size),
        getTelemetry(id),
        getDecisions(id),
      ]);
      terrainCache.current = layers;
      setRequest((current) => ({ ...current, ...config, body, seed: loaded.seed }) as MissionRequest);
      setSessionId(id);
      setDecisions(decisionList);
      setBelief(null);
      setSummary(loaded);
      setTerrain(layers);
      setFrames(telemetry);
      setIndex((current) => clampIndex(opts.keepFrame ? current : (opts.frame ?? 0), telemetry.length));
      if (opts.camera) setCameraMode(opts.camera);
      return telemetry.length;
    },
    [],
  );

  const fail = useCallback((caught: unknown, fallback: string) => {
    setError(caught instanceof ApiError ? caught.message : fallback);
    setStatus("failed");
  }, []);

  const launch = useCallback(async () => {
    setBusy(true);
    setError(null);
    setStatus("running simulation on the engine…");
    setPlaying(false);
    try {
      const started = await startMission(request);
      const n = await loadSession(started.session_id);
      setPaired(null);
      setDemo(null);
      setPins([]);
      setStatus(`mission loaded · ${n} frames`);
      setPlaying(true);
    } catch (caught) {
      fail(caught, "unexpected error contacting the engine");
    } finally {
      setBusy(false);
    }
  }, [request, loadSession, fail]);

  const openDemo = useCallback(async () => {
    setBusy(true);
    setError(null);
    setPlaying(false);
    setStatus("loading the demonstration mission…");
    try {
      const d = await getDemoMission();
      if (!d.chosen) throw new ApiError("no demonstration mission has been selected");
      const started = await startMission(d.request);
      const n = await loadSession(started.session_id, { frame: d.chosen.start_frame, camera: "planner" });
      setDemo(d);
      setPaired(null);
      setPins([]);
      setStatus(`demonstration mission · ${n} frames · press play`);
    } catch (caught) {
      fail(caught, "could not load the demonstration mission");
    } finally {
      setBusy(false);
    }
  }, [loadSession, fail]);

  const openPaired = useCallback(
    async (condition: string, seed: number) => {
      setStatus("re-running both planners on the confirmatory seed…");
      try {
        const replay = await getPairedReplay(condition, seed);
        const n = await loadSession(replay.runs[1].session_id);
        setPaired(replay);
        setPairedActive(1);
        setDemo(null);
        setStatus(`paired replay · ${n} frames`);
      } catch (caught) {
        fail(caught, "could not load that paired seed");
      }
    },
    [loadSession, fail],
  );

  const selectPaired = useCallback(
    async (i: number) => {
      if (!paired || i === pairedActive) return;
      setPlaying(false);
      setPairedActive(i);
      try {
        await loadSession(paired.runs[i].session_id, { keepFrame: true });
      } catch (caught) {
        fail(caught, "could not switch planner");
      }
    },
    [paired, pairedActive, loadSession, fail],
  );

  // Deep links (see the header comment).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("session");
    const pair = params.get("paired");
    let cancelled = false;
    (async () => {
      try {
        if (params.get("demo")) {
          await openDemo();
        } else if (pair) {
          const [condition, seed] = pair.split(":");
          await openPaired(condition, Number(seed));
        } else if (id) {
          const startCamera = params.get("camera") as CameraMode | null;
          const n = await loadSession(id, {
            frame: Number(params.get("frame") ?? 0),
            camera: startCamera && CAMERA_ORDER.includes(startCamera) ? startCamera : undefined,
          });
          if (!cancelled) setStatus(`replaying ${id.slice(0, 24)}… · ${n} frames`);
        }
      } catch (caught) {
        if (cancelled) return;
        setError(
          caught instanceof ApiError
            ? `${caught.message} - the engine keeps only recent missions; reopen it from its source page.`
            : "could not load that mission",
        );
        setStatus("failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadSession, openDemo, openPaired]);

  // Playback clock. Frames are already computed; this only paces them.
  useEffect(() => {
    if (timer.current) clearInterval(timer.current);
    if (!playing || frames.length === 0) return;
    timer.current = setInterval(() => {
      setIndex((current) => {
        if (current >= frames.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, speed);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [playing, speed, frames.length]);

  const frame = frames[index] ?? null;

  // One belief fetch in flight at a time; when it lands, if the playhead has
  // moved, fetch again for wherever it is now. Cancelled only when the
  // session changes.
  const beliefInFlight = useRef(false);
  const wantedIndex = useRef(0);
  const beliefSession = useRef<string | null>(null);
  const pullBelief = useCallback(async (sid: string) => {
    if (beliefInFlight.current) return;
    beliefInFlight.current = true;
    let target = wantedIndex.current;
    try {
      for (;;) {
        const snap = await getBelief(sid, target);
        if (beliefSession.current !== sid) return;
        setBelief(snap);
        if (wantedIndex.current === target) return;
        target = wantedIndex.current;
      }
    } catch {
      /* belief only decorates the view; the mission still plays without it */
    } finally {
      beliefInFlight.current = false;
    }
  }, []);
  useEffect(() => {
    beliefSession.current = sessionId;
  }, [sessionId]);
  useEffect(() => {
    wantedIndex.current = index;
    if (sessionId) void pullBelief(sessionId);
  }, [index, sessionId, pullBelief]);

  const hoverProbe = useProbe(sessionId, hoverCell?.[0] ?? null, hoverCell?.[1] ?? null, index);
  const probeA = useProbe(sessionId, pins[0]?.[0] ?? null, pins[0]?.[1] ?? null, index);
  const probeB = useProbe(sessionId, pins[1]?.[0] ?? null, pins[1]?.[1] ?? null, index);
  const probeColumns: ProbeColumn[] = pins.length
    ? [
        ...(probeA ? [{ tag: "A", data: probeA }] : []),
        ...(probeB ? [{ tag: "B", data: probeB }] : []),
      ]
    : hoverProbe
      ? [{ tag: "CELL", data: hoverProbe }]
      : [];
  const pin = useCallback((cell: [number, number]) => {
    setPins((current) => (current.length >= 2 ? [cell] : [...current, cell]));
  }, []);

  const decision =
    frame && frame.decision_index >= 0 ? (decisions[frame.decision_index] ?? null) : null;
  const trail = useMemo(
    () => frames.slice(0, index + 1).map((f) => [f.row, f.col] as [number, number]),
    [frames, index],
  );
  const plannerInfo = planners.find((p) => p.name === request.planner);
  const riskBudget =
    typeof summary?.provenance?.config.risk_budget === "number" ? summary.provenance.config.risk_budget : null;

  const events = useMemo(
    () => buildReplayEvents(frames, decisions, summary),
    [frames, decisions, summary],
  );
  const caption = latestEvent(events, index);

  const seek = useCallback((i: number) => {
    setPlaying(false);
    setIndex(i);
  }, []);

  const present = useCallback(() => {
    // presenting starts on the natural-colour surface, whatever layer was up
    setLayer("surface");
    setPresenting(true);
  }, []);

  // Presentation keys: 1-5 camera, space play/pause, arrows step, L layer,
  // T switch planner (paired replay), Esc exit.
  useEffect(() => {
    if (!presenting) return;
    const available = LAYERS.filter((l) => !l.needsBelief || belief).map((l) => l.key);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPresenting(false);
      else if (e.key === " ") {
        e.preventDefault();
        setPlaying((p) => !p);
      } else if (e.key === "ArrowRight") seek(Math.min(frames.length - 1, index + 1));
      else if (e.key === "ArrowLeft") seek(Math.max(0, index - 1));
      else if (/^[1-5]$/.test(e.key)) setCameraMode(CAMERA_ORDER[Number(e.key) - 1]);
      else if (e.key.toLowerCase() === "l") {
        setLayer((current) => available[(available.indexOf(current) + 1) % available.length]);
      } else if (e.key.toLowerCase() === "t" && paired) void selectPaired(pairedActive === 0 ? 1 : 0);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [presenting, frames.length, index, seek, belief, paired, pairedActive, selectPaired]);

  const scene = terrain ? (
    <MissionScene
      terrain={terrain}
      summary={summary}
      frame={frame}
      trail={trail}
      layer={layer}
      belief={belief}
      opacity={opacity}
      cameraMode={cameraMode}
      decision={decision}
      showCandidates={cameraMode === "planner"}
      hoverCell={presenting ? null : hoverCell}
      pins={presenting ? [] : pins}
      onHover={presenting ? () => undefined : setHoverCell}
      onPin={presenting ? undefined : pin}
    />
  ) : null;

  if (presenting && terrain && summary) {
    const target = decision?.candidates.find((c) => c.selected);
    return (
      <main className="relative flex h-screen flex-col overflow-hidden bg-black">
        <div className="relative min-h-0 flex-1">
          {scene}
          <div className="pointer-events-none absolute left-4 top-4">
            <div className="font-mono text-[13px] tracking-[0.3em] text-slate-100">EXONAUT</div>
            <div className="mt-1 font-mono text-[11px] tracking-[0.14em] text-slate-400">
              {summary.body.toUpperCase()} · {plannerInfo?.label ?? summary.planner} · seed {summary.seed}
            </div>
            {demo ? (
              <div className="mt-1 font-mono text-[10px] tracking-[0.18em] text-sky-300">DEMONSTRATION CASE</div>
            ) : null}
            {layer !== "surface" ? (
              <div className="mt-1 font-mono text-[10px] tracking-[0.18em] text-slate-300">
                LAYER {LAYER_BY_KEY[layer].label}
              </div>
            ) : null}
          </div>
          <div className="absolute right-4 top-4 flex flex-col items-end gap-2">
            <div className="flex gap-1">
              <CameraBar mode={cameraMode} onMode={setCameraMode} showKeys />
              <button
                onClick={() => setPresenting(false)}
                className="rounded-sm border border-white/20 bg-black/60 px-2 py-1 font-mono text-[9px] tracking-[0.16em] text-slate-300"
              >
                EXIT (ESC)
              </button>
            </div>
            {paired ? <PairedBar paired={paired} active={pairedActive} onSelect={selectPaired} /> : null}
            {cameraMode === "navcam" ? <NavcamReadout frame={frame} /> : null}
            {cameraMode === "planner" ? <RouteLegend planner riskBudget={riskBudget} /> : null}
          </div>
          {caption ? (
            <div className="pointer-events-none absolute inset-x-0 bottom-9 flex justify-center">
              <div className="rounded-sm border border-white/15 bg-black/70 px-4 py-2 font-mono text-[15px] tracking-[0.06em] text-slate-100">
                <span className="mr-3 text-slate-500">T+{String(caption.step).padStart(4, "0")}</span>
                {caption.text}
              </div>
            </div>
          ) : null}
          <div className="pointer-events-none absolute bottom-2 left-4 font-mono text-[9px] tracking-[0.14em] text-slate-500">
            1–5 CAMERA · SPACE PLAY · ← → STEP · L LAYER{paired ? " · T PLANNER" : ""} · ESC EXIT
          </div>
        </div>
        <div className="grid grid-cols-6 gap-px border-t border-white/10 bg-white/10">
          {[
            ["BATTERY", frame ? `${(frame.charge_fraction * 100).toFixed(0)}%` : "—"],
            ["LAST TRIP P(FAIL)", frame ? frame.predicted_failure_prob.toFixed(3) : "—"],
            ["TARGET", target ? `TGT ${String(target.target_id).padStart(2, "0")}` : frame?.returning ? "LANDER" : "—"],
            ["DECISION", frame ? (frame.returning ? "RETURNING" : frame.reason === "slip_no_progress" ? "REPLANNING" : "PURSUING") : "—"],
            ["SCIENCE", frame ? `${frame.targets_visited}/${summary.targets_total}` : "—"],
            ["STEP", frame ? `T+${String(frame.step).padStart(4, "0")}` : "—"],
          ].map(([label, value]) => (
            <div key={label} className="bg-[#07090d] px-4 py-3">
              <div className="font-mono text-[10px] tracking-[0.2em] text-slate-500">{label}</div>
              <div className="font-mono text-[26px] tabular-nums text-slate-100">{value}</div>
            </div>
          ))}
        </div>
        <Timeline
          frameCount={frames.length}
          index={index}
          onSeek={seek}
          playing={playing}
          onTogglePlay={() => setPlaying((p) => !p)}
          speed={speed}
          onSpeed={setSpeed}
          events={events}
        />
      </main>
    );
  }

  const columns = `${leftOpen ? "260px" : "26px"} minmax(0,1fr) ${rightOpen ? "280px" : "26px"}`;

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-[#07090d]">
      <Nav />
      <MissionHeader summary={summary} step={frame?.step ?? 0} total={summary?.steps ?? 0} />

      <div
        className="grid min-h-0 flex-1 grid-cols-1 gap-2 p-2 lg:[grid-template-columns:var(--cols)]"
        style={{ "--cols": columns } as CSSProperties}
      >
        {/* ---------------- left: mission setup ---------------- */}
        {leftOpen ? (
          <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
            <button
              onClick={() => setLeftOpen(false)}
              className="hidden self-end font-mono text-[8.5px] tracking-[0.18em] text-slate-500 hover:text-slate-300 lg:block"
            >
              ‹ HIDE
            </button>
            <Panel title="Mission Setup">
              <div className="space-y-2">
                <button
                  onClick={openDemo}
                  disabled={busy}
                  title="Loads one validation mission chosen by a written rule to show an adaptation event"
                  className="w-full rounded-sm border border-sky-400/40 bg-sky-400/10 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.2em] text-sky-200 transition hover:bg-sky-400/20 disabled:opacity-40"
                >
                  demo mission
                </button>
                <p className="font-mono text-[8.5px] leading-relaxed text-slate-500">
                  A demonstration case selected by rule from validation seeds. It illustrates one
                  adaptation event and is not a result.
                </p>

                <label className="block border-t border-white/10 pt-2">
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">Body</span>
                  <select
                    value={request.body}
                    onChange={(e) => setRequest({ ...request, body: e.target.value as MissionRequest["body"] })}
                    className="mt-1 w-full rounded-sm border border-white/10 bg-black/40 px-2 py-1 font-mono text-[11px] text-slate-200"
                  >
                    <option value="mars">MARS (out-of-distribution)</option>
                    <option value="moon">MOON (in-distribution)</option>
                  </select>
                </label>

                <label className="block">
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">Planner</span>
                  <select
                    value={request.planner}
                    onChange={(e) => setRequest({ ...request, planner: e.target.value })}
                    className="mt-1 w-full rounded-sm border border-white/10 bg-black/40 px-2 py-1 font-mono text-[11px] text-slate-200"
                  >
                    {planners.map((p) => (
                      <option key={p.name} value={p.name}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </label>
                {plannerInfo ? (
                  <p className="font-mono text-[9px] leading-relaxed text-slate-500">{plannerInfo.description}</p>
                ) : null}

                <label className="block">
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">Engine</span>
                  <select
                    value={request.engine}
                    onChange={(e) => setRequest({ ...request, engine: e.target.value as MissionRequest["engine"] })}
                    className="mt-1 w-full rounded-sm border border-white/10 bg-black/40 px-2 py-1 font-mono text-[11px] text-slate-200"
                  >
                    <option value="v1">v1 · confirmatory engine</option>
                    <option value="v2">v2 · fixed (exploratory)</option>
                  </select>
                </label>
                <p className="font-mono text-[9px] leading-relaxed text-slate-500">
                  {request.engine === "v1"
                    ? "The engine the published results were produced with, including its known defects."
                    : "Calibrated learner, faults inside the mission, independent random streams, no intervention ratchet, no lander livelock. Exploratory: no confirmatory result uses it."}
                </p>

                <label className="block">
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">Terrain seed</span>
                  <input
                    type="number"
                    value={request.seed}
                    onChange={(e) => setRequest({ ...request, seed: Number(e.target.value) })}
                    className="mt-1 w-full rounded-sm border border-white/10 bg-black/40 px-2 py-1 font-mono text-[11px] text-slate-200"
                  />
                </label>

                {[
                  { key: "size", label: "Map size", min: 24, max: 96, step: 8 },
                  { key: "n_targets", label: "Targets", min: 1, max: 8, step: 1 },
                  { key: "max_steps", label: "Step budget", min: 100, max: 1200, step: 100 },
                  { key: "fault_rate", label: "Fault rate", min: 0, max: 3, step: 0.5 },
                  { key: "comm_delay", label: "Comm delay", min: 0, max: 40, step: 5 },
                  { key: "risk_budget", label: "Risk budget ε", min: 0.02, max: 0.6, step: 0.02 },
                ].map((control) => (
                  <label key={control.key} className="block">
                    <span className="flex items-baseline justify-between font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">
                      {control.label}
                      <span className="tabular-nums text-slate-300">
                        {(request as unknown as Record<string, number>)[control.key]}
                      </span>
                    </span>
                    <input
                      type="range"
                      min={control.min}
                      max={control.max}
                      step={control.step}
                      value={(request as unknown as Record<string, number>)[control.key]}
                      onChange={(e) => setRequest({ ...request, [control.key]: Number(e.target.value) })}
                      className="mt-1 w-full accent-orange-500"
                    />
                  </label>
                ))}

                <button
                  onClick={launch}
                  disabled={busy}
                  className="mt-2 w-full rounded-sm border border-orange-500/40 bg-orange-500/10 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.2em] text-orange-300 transition hover:bg-orange-500/20 disabled:opacity-40"
                >
                  {busy ? "running…" : "launch mission"}
                </button>
                <p className="font-mono text-[9px] text-slate-600">{status}</p>
                {error ? (
                  <p className="rounded-sm border border-rose-500/30 bg-rose-500/10 p-2 font-mono text-[9px] leading-relaxed text-rose-300">
                    {error}
                  </p>
                ) : null}
              </div>
            </Panel>

            {summary?.provenance ? (
              <Panel title="Provenance">
                <ProvenancePanel provenance={summary.provenance} />
              </Panel>
            ) : null}

            {splits.length ? (
              <Panel title="Seed Protocol">
                {splits.map((split) => (
                  <Readout
                    key={split.name}
                    label={split.name}
                    value={`${split.first}…${split.last}`}
                    tone={split.quarantined.length ? "warn" : "normal"}
                  />
                ))}
                <p className="mt-2 border-t border-white/10 pt-2 font-mono text-[9px] leading-relaxed text-slate-500">
                  Splits are frozen and checksummed. Seeds consumed by the early pilot are quarantined
                  and excluded from confirmatory results.
                </p>
              </Panel>
            ) : null}
          </div>
        ) : (
          <Rail label="MISSION SETUP" side="left" onOpen={() => setLeftOpen(true)} />
        )}

        {/* ---------------- centre: the world ---------------- */}
        <div className="flex min-h-0 flex-col gap-1.5">
          {demo ? <DemoBanner demo={demo} summary={summary} /> : null}
          {paired ? <PairedBar paired={paired} active={pairedActive} onSelect={selectPaired} /> : null}
          <div className="relative min-h-0 flex-1 overflow-hidden rounded-sm border border-white/10">
            {scene ?? <SceneFallback label="launch a mission, or load the demo mission, to render the surface" />}

            <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-2">
              <div className="pointer-events-auto rounded-sm border border-white/10 bg-black/45 p-1.5 backdrop-blur-sm">
                <LayerBar
                  layer={layer}
                  onLayer={setLayer}
                  opacity={opacity}
                  onOpacity={setOpacity}
                  hasBelief={Boolean(belief)}
                />
              </div>
              <div className="pointer-events-auto flex flex-col items-end gap-1.5">
                <div className="flex gap-1">
                  <CameraBar mode={cameraMode} onMode={setCameraMode} />
                  <button
                    onClick={() => {
                      const focus = leftOpen || rightOpen;
                      setLeftOpen(!focus);
                      setRightOpen(!focus);
                    }}
                    className="rounded-sm border border-white/10 bg-black/55 px-2 py-1 font-mono text-[9px] tracking-[0.16em] text-slate-400 hover:text-slate-200"
                    title="Hide or show both side columns"
                  >
                    {leftOpen || rightOpen ? "FOCUS" : "PANELS"}
                  </button>
                  {summary ? (
                    <button
                      onClick={present}
                      className="rounded-sm border border-orange-500/50 bg-orange-500/15 px-2 py-1 font-mono text-[9px] tracking-[0.16em] text-orange-300 hover:bg-orange-500/25"
                      title="Full-screen view for presenting (Esc to exit)"
                    >
                      PRESENT
                    </button>
                  ) : null}
                </div>
                {summary ? (
                  <div className="rounded-sm border border-white/10 bg-black/60 px-3 py-1.5 text-right">
                    <div className="font-mono text-[9px] tracking-[0.16em] text-slate-500">OUTCOME</div>
                    <div
                      className={`font-mono text-[12px] tracking-[0.12em] ${
                        summary.success ? "text-emerald-300" : "text-rose-400"
                      }`}
                    >
                      {summary.success ? "RETURNED SAFELY" : summary.termination.replace("_", " ").toUpperCase()}
                    </div>
                    <div className="font-mono text-[10px] tabular-nums text-slate-300">
                      science {(summary.science_fraction * 100).toFixed(0)}% · {summary.targets_visited}/
                      {summary.targets_total} targets
                    </div>
                  </div>
                ) : null}
                {cameraMode === "navcam" ? <NavcamReadout frame={frame} /> : null}
                {summary && cameraMode !== "navcam" ? (
                  <RouteLegend planner={cameraMode === "planner"} riskBudget={riskBudget} />
                ) : null}
                {cameraMode === "planner" && decision ? (
                  <div className="max-w-[240px] rounded-sm border border-white/10 bg-black/60 px-2 py-1 font-mono text-[8.5px] leading-snug text-slate-400">
                    Decision at T+{String(decision.step).padStart(4, "0")}: every candidate route the planner
                    evaluated, coloured by its own verdict. Details in the Autonomy Inspector.
                  </div>
                ) : null}
              </div>
            </div>

            {terrain ? (
              <div className="pointer-events-none absolute bottom-12 left-2 flex flex-col gap-2">
                <div className="pointer-events-auto">
                  <Legend
                    layer={layer}
                    terrain={terrain}
                    exaggeration={verticalExaggeration(terrain)}
                    beliefStep={LAYER_BY_KEY[layer].needsBelief ? (belief?.step ?? null) : null}
                    constants={constants}
                    riskBudget={riskBudget}
                  />
                </div>
              </div>
            ) : null}
            {terrain && probeColumns.length ? (
              <div className="pointer-events-none absolute bottom-12 right-2">
                <ProbePanel columns={probeColumns} pinned={pins.length > 0} onClear={() => setPins([])} />
              </div>
            ) : null}

            {frames.length > 0 ? (
              <div className="absolute inset-x-0 bottom-0">
                <Timeline
                  frameCount={frames.length}
                  index={index}
                  onSeek={seek}
                  playing={playing}
                  onTogglePlay={() => setPlaying((p) => !p)}
                  speed={speed}
                  onSpeed={setSpeed}
                  events={events}
                />
              </div>
            ) : null}
          </div>
        </div>

        {/* ---------------- right: telemetry ---------------- */}
        {rightOpen ? (
          <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
            <button
              onClick={() => setRightOpen(false)}
              className="hidden self-start font-mono text-[8.5px] tracking-[0.18em] text-slate-500 hover:text-slate-300 lg:block"
            >
              HIDE ›
            </button>
            <Panel title="Rover Status" right={<StatusBadge status="SIMULATED" />}>
              <RoverStatus frame={frame} />
            </Panel>
            <Panel title="Autonomy" right={<StatusBadge status="INFERRED" />}>
              <AutonomyPanel
                frame={frame}
                plannerLabel={plannerInfo?.label ?? request.planner}
                adaptive={plannerInfo?.adaptive ?? false}
              />
            </Panel>
            <Panel
              title="Terrain Model"
              right={
                <span className="flex gap-1">
                  <StatusBadge status="INFERRED" />
                  <StatusBadge status="SIMULATED" />
                </span>
              }
            >
              <BeliefPanel
                frame={frame}
                trueSlip={summary?.true_class_slip ?? {}}
                adaptive={plannerInfo?.adaptive ?? false}
              />
            </Panel>
            <Panel title="Mission Replay">
              <ReplayLog events={events} index={index} onSeek={seek} />
            </Panel>
          </div>
        ) : (
          <Rail label="TELEMETRY" side="right" onOpen={() => setRightOpen(true)} />
        )}
      </div>
    </main>
  );
}

"use client";

/**
 * MISSION CONTROL — the demo surface.
 *
 * Everything shown here is produced by the Python engine and delivered over
 * the API. The page holds no simulation logic; it schedules playback and
 * draws state.
 */

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { verticalExaggeration } from "@/components/TerrainMesh";
import {
  CameraBar,
  LayerBar,
  Legend,
  ProbePanel,
  ProvenancePanel,
} from "@/components/MapOverlays";
import { Nav } from "@/components/Nav";
import {
  AutonomyPanel,
  BeliefPanel,
  EventLog,
  MissionHeader,
  Panel,
  Readout,
  RoverStatus,
} from "@/components/Panels";
import {
  DEFAULT_MISSION,
  getBelief,
  getDecisions,
  getPlanners,
  getSplits,
  getTerrain,
  startMission,
  getTelemetry,
  ApiError,
} from "@/lib/api";
import { LAYER_BY_KEY } from "@/lib/layers";
import type {
  BeliefSnapshot,
  CameraMode,
  Decision,
  MissionRequest,
  MissionSummary,
  PlannerInfo,
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



interface LoggedEvent {
  step: number;
  text: string;
  tone: string;
}

export default function MissionControl() {
  const [planners, setPlanners] = useState<PlannerInfo[]>([]);
  const [splits, setSplits] = useState<SplitInfo[]>([]);
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
  const [probeCell, setProbeCell] = useState<[number, number] | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    getPlanners().then(setPlanners).catch(() => undefined);
    getSplits().then(setSplits).catch(() => undefined);
  }, []);

  const launch = useCallback(async () => {
    setBusy(true);
    setError(null);
    setStatus("running simulation on the engine…");
    setPlaying(false);
    try {
      const [started, layers] = await Promise.all([
        startMission(request),
        getTerrain(request.body, request.seed, request.size),
      ]);
      const [telemetry, decisionList] = await Promise.all([
        getTelemetry(started.session_id),
        getDecisions(started.session_id),
      ]);
      setSessionId(started.session_id);
      setDecisions(decisionList);
      setBelief(null);
      setSummary(started.summary);
      setTerrain(layers);
      setFrames(telemetry);
      setIndex(0);
      setStatus(`mission loaded · ${telemetry.length} frames`);
      setPlaying(true);
    } catch (caught) {
      const message =
        caught instanceof ApiError ? caught.message : "unexpected error contacting the engine";
      setError(message);
      setStatus("failed");
    } finally {
      setBusy(false);
    }
  }, [request]);

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

  // One fetch in flight at a time. When it lands, if the playhead has moved,
  // fetch again for wherever it is now - so the belief keeps up with playback
  // without firing a request per frame. Cancelled only when the session
  // changes; cancelling on every frame (the first version) stranded the view
  // on a stale snapshot.
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

  const decision =
    frame && frame.decision_index >= 0 ? (decisions[frame.decision_index] ?? null) : null;
  const trail = useMemo(
    () => frames.slice(0, index + 1).map((f) => [f.row, f.col] as [number, number]),
    [frames, index],
  );

  const plannerInfo = planners.find((p) => p.name === request.planner);

  const events = useMemo<LoggedEvent[]>(() => {
    const log: LoggedEvent[] = [];
    let lastTargets = 0;
    let lastInterventions = 0;
    let lastReturning = false;
    frames.slice(0, index + 1).forEach((f) => {
      if (f.targets_visited > lastTargets) {
        log.push({ step: f.step, text: `Science target acquired (${f.targets_visited})`, tone: "good" });
        lastTargets = f.targets_visited;
      }
      if (f.interventions > lastInterventions) {
        log.push({ step: f.step, text: "No viable route — ground intervention requested", tone: "warn" });
        lastInterventions = f.interventions;
      }
      if (f.returning !== lastReturning) {
        log.push({
          step: f.step,
          text: f.returning ? "Objective abandoned — returning to lander" : "New objective selected",
          tone: f.returning ? "warn" : "normal",
        });
        lastReturning = f.returning;
      }
      if (f.reason === "slip_no_progress") {
        log.push({ step: f.step, text: `Severe slip ${f.slip.toFixed(2)} — replanning`, tone: "bad" });
      }
      if (f.reason === "hazard_refused") {
        log.push({ step: f.step, text: "Hazard refused by onboard check", tone: "warn" });
      }
    });
    return log.slice(-120);
  }, [frames, index]);

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-[#07090d]">
      <Nav />
      <MissionHeader summary={summary} step={frame?.step ?? 0} total={summary?.steps ?? 0} />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 p-2 lg:grid-cols-[260px_1fr_280px]">
        {/* ---------------- left: mission setup ---------------- */}
        <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
          <Panel title="Mission Setup">
            <div className="space-y-2">
              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">
                  Body
                </span>
                <select
                  value={request.body}
                  onChange={(e) =>
                    setRequest({ ...request, body: e.target.value as MissionRequest["body"] })
                  }
                  className="mt-1 w-full rounded-sm border border-white/10 bg-black/40 px-2 py-1 font-mono text-[11px] text-slate-200"
                >
                  <option value="mars">MARS (out-of-distribution)</option>
                  <option value="moon">MOON (in-distribution)</option>
                </select>
              </label>

              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">
                  Planner
                </span>
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
                <p className="font-mono text-[9px] leading-relaxed text-slate-500">
                  {plannerInfo.description}
                </p>
              ) : null}

              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">
                  Terrain seed
                </span>
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
                    <span className="text-slate-300 tabular-nums">
                      {(request as unknown as Record<string, number>)[control.key]}
                    </span>
                  </span>
                  <input
                    type="range"
                    min={control.min}
                    max={control.max}
                    step={control.step}
                    value={(request as unknown as Record<string, number>)[control.key]}
                    onChange={(e) =>
                      setRequest({ ...request, [control.key]: Number(e.target.value) })
                    }
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
                Splits are frozen and checksummed. Seeds consumed by the early
                pilot are quarantined and excluded from confirmatory results.
              </p>
            </Panel>
          ) : null}
        </div>

        {/* ---------------- centre: the world ---------------- */}
        <div className="relative min-h-0 overflow-hidden rounded-sm border border-white/10">
          {terrain ? (
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
              probeCell={probeCell}
              onProbe={setProbeCell}
            />
          ) : (
            <SceneFallback label="launch a mission to render the surface" />
          )}

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
              <CameraBar mode={cameraMode} onMode={setCameraMode} />
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
              {cameraMode === "planner" && decision ? (
                <div className="max-w-[260px] rounded-sm border border-white/10 bg-black/60 px-2 py-1.5 font-mono text-[9px] leading-snug text-slate-400">
                  Decision at T+{String(decision.step).padStart(4, "0")}: every route evaluated.
                  <span className="text-emerald-300"> Solid green</span> = chosen,
                  <span className="text-slate-300"> dashed grey</span> = within budget,
                  <span className="text-rose-300"> dashed red</span> = P(fail) over ε = {decision.risk_budget}.
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
                />
              </div>
            </div>
          ) : null}
          {terrain && probeCell ? (
            <div className="pointer-events-none absolute bottom-12 right-2">
              <ProbePanel terrain={terrain} belief={belief} cell={probeCell} request={request} />
            </div>
          ) : null}

          {frames.length > 0 ? (
            <div className="absolute inset-x-0 bottom-0 flex items-center gap-3 border-t border-white/10 bg-[#0b0e14]/92 px-3 py-2">
              <button
                onClick={() => setPlaying((p) => !p)}
                className="rounded-sm border border-white/15 px-3 py-1 font-mono text-[10px] tracking-[0.18em] text-slate-200 hover:bg-white/5"
              >
                {playing ? "PAUSE" : "PLAY"}
              </button>
              <input
                type="range"
                min={0}
                max={Math.max(frames.length - 1, 0)}
                value={index}
                onChange={(e) => {
                  setPlaying(false);
                  setIndex(Number(e.target.value));
                }}
                className="flex-1 accent-orange-500"
              />
              <span className="font-mono text-[10px] tabular-nums text-slate-400">
                {String(index + 1).padStart(4, "0")}/{String(frames.length).padStart(4, "0")}
              </span>
              <select
                value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))}
                className="rounded-sm border border-white/10 bg-black/40 px-2 py-1 font-mono text-[10px] text-slate-300"
              >
                <option value={220}>0.5x</option>
                <option value={90}>1x</option>
                <option value={40}>2x</option>
                <option value={14}>6x</option>
              </select>
            </div>
          ) : null}
        </div>

        {/* ---------------- right: telemetry ---------------- */}
        <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
          <Panel title="Rover Status">
            <RoverStatus frame={frame} />
          </Panel>
          <Panel title="Autonomy">
            <AutonomyPanel
              frame={frame}
              plannerLabel={plannerInfo?.label ?? request.planner}
              adaptive={plannerInfo?.adaptive ?? false}
            />
          </Panel>
          <Panel title="Terrain Model">
            <BeliefPanel
              frame={frame}
              trueSlip={summary?.true_class_slip ?? {}}
              adaptive={plannerInfo?.adaptive ?? false}
            />
          </Panel>
          <Panel title="Event Log">
            <EventLog events={events} />
          </Panel>
        </div>
      </div>
    </main>
  );
}

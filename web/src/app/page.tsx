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
  StatusBadge,
  Legend,
  ProbePanel,
  ProvenancePanel,
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
  getPlanners,
  getSplits,
  getSummary,
  getTerrain,
  startMission,
  getTelemetry,
  ApiError,
} from "@/lib/api";
import { LAYER_BY_KEY } from "@/lib/layers";
import { buildReplayEvents, latestEvent } from "@/lib/replay";
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

  // Deep link: /?session=<id> opens a mission the engine already ran (for
  // example a case study from Failure Analysis) instead of starting a new one.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("session");
    if (!id) return;
    const startFrame = Number(params.get("frame") ?? 0);
    const startCamera = params.get("camera") as CameraMode | null;
    let cancelled = false;
    (async () => {
      try {
        const loaded = await getSummary(id);
        const config = (loaded.provenance?.config ?? {}) as Partial<MissionRequest>;
        const body = (config.body ?? loaded.body) as MissionRequest["body"];
        const size = Number(config.size ?? 56);
        const [layers, telemetry, decisionList] = await Promise.all([
          getTerrain(body, loaded.seed, size),
          getTelemetry(id),
          getDecisions(id),
        ]);
        if (cancelled) return;
        setRequest((current) => ({ ...current, ...config, body, seed: loaded.seed }) as MissionRequest);
        setSessionId(id);
        setDecisions(decisionList);
        setBelief(null);
        setSummary(loaded);
        setTerrain(layers);
        setFrames(telemetry);
        setIndex(Math.min(Math.max(0, Number.isFinite(startFrame) ? startFrame : 0), telemetry.length - 1));
        if (startCamera && ["orbit", "chase", "top", "pov", "planner"].includes(startCamera)) {
          setCameraMode(startCamera);
        }
        setStatus(`replaying ${id.slice(0, 24)}… · ${telemetry.length} frames`);
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
  }, []);

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

  const events = useMemo(
    () => buildReplayEvents(frames, decisions, summary),
    [frames, decisions, summary],
  );
  const caption = latestEvent(events, index);

  const [presenting, setPresenting] = useState(false);
  const seek = useCallback((i: number) => {
    setPlaying(false);
    setIndex(i);
  }, []);

  // Presentation-mode keys: space play/pause, arrows step, 1-5 camera, Esc exit.
  useEffect(() => {
    if (!presenting) return;
    const cams: CameraMode[] = ["orbit", "chase", "top", "pov", "planner"];
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPresenting(false);
      else if (e.key === " ") {
        e.preventDefault();
        setPlaying((p) => !p);
      } else if (e.key === "ArrowRight") seek(Math.min(frames.length - 1, index + 1));
      else if (e.key === "ArrowLeft") seek(Math.max(0, index - 1));
      else if (/^[1-5]$/.test(e.key)) setCameraMode(cams[Number(e.key) - 1]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [presenting, frames.length, index, seek]);

  if (presenting && terrain && summary) {
    const chosen = frame && frame.decision_index >= 0 ? decisions[frame.decision_index] : null;
    const target = chosen?.candidates.find((c) => c.selected);
    return (
      <main className="relative flex h-screen flex-col overflow-hidden bg-black">
        <div className="relative min-h-0 flex-1">
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
            probeCell={null}
            onProbe={() => undefined}
          />
          <div className="pointer-events-none absolute left-4 top-4">
            <div className="font-mono text-[13px] tracking-[0.3em] text-slate-100">EXONAUT</div>
            <div className="mt-1 font-mono text-[11px] tracking-[0.14em] text-slate-400">
              {summary.body.toUpperCase()} · {plannerInfo?.label ?? summary.planner} · seed{" "}
              {summary.seed}
            </div>
          </div>
          <div className="absolute right-4 top-4 flex gap-1">
            <CameraBar mode={cameraMode} onMode={setCameraMode} />
            <button
              onClick={() => setPresenting(false)}
              className="rounded-sm border border-white/20 bg-black/60 px-2 py-1 font-mono text-[9px] tracking-[0.16em] text-slate-300"
            >
              EXIT (ESC)
            </button>
          </div>
          {caption ? (
            <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
              <div className="rounded-sm border border-white/15 bg-black/70 px-4 py-2 font-mono text-[15px] tracking-[0.06em] text-slate-100">
                <span className="mr-3 text-slate-500">T+{String(caption.step).padStart(4, "0")}</span>
                {caption.text}
              </div>
            </div>
          ) : null}
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
              <div className="flex gap-1">
                <CameraBar mode={cameraMode} onMode={setCameraMode} />
                {summary ? (
                  <button
                    onClick={() => setPresenting(true)}
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

        {/* ---------------- right: telemetry ---------------- */}
        <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
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
      </div>
    </main>
  );
}

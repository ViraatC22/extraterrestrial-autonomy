/**
 * Client for the EXONAUT engine.
 *
 * Every call here reaches the Python research engine. The frontend holds no
 * simulation logic of its own, which is what keeps the interface and the
 * experiments in agreement.
 */

import type {
  BeliefSnapshot,
  DemoMission,
  FailuresPayload,
  Decision,
  ModelConstants,
  PairedReplay,
  ProbePayload,
  MissionRequest,
  MissionStarted,
  MissionSummary,
  PlannerInfo,
  ResultsPayload,
  SplitInfo,
  TelemetryFrame,
  TerrainLayers,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_EXONAUT_API ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      `Cannot reach the EXONAUT engine at ${API_BASE}. Start it with:  ` +
        `uvicorn exonaut.api:app --port 8000`,
    );
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const DEFAULT_MISSION: MissionRequest = {
  body: "mars",
  planner: "adaptive_risk_aware_astar",
  seed: 200000,
  size: 56,
  n_targets: 4,
  max_steps: 600,
  risk_budget: 0.2,
  fault_rate: 0,
  comm_delay: 0,
  terrain_uncertainty: 1,
  sensor_noise_scale: 1,
  sensing_radius: 6,
  solar_rate: 2,
  energy_reserve_fraction: 0.25,
  prior_body: "moon",
  engine: "v1",
};

export const getHealth = () => request<{ status: string }>("/health");
export const getPlanners = () => request<PlannerInfo[]>("/planners");
export const getSplits = () => request<SplitInfo[]>("/splits");

export const getTerrain = (body: string, seed: number, size: number) =>
  request<TerrainLayers>(`/terrain?body=${body}&seed=${seed}&size=${size}`);

export const startMission = (mission: MissionRequest) =>
  request<MissionStarted>("/start-mission", {
    method: "POST",
    body: JSON.stringify(mission),
  });

export const getSummary = (sessionId: string) =>
  request<MissionSummary>(`/missions/${sessionId}`);

export const getTelemetry = async (sessionId: string) => {
  const frames = await request<TelemetryFrame[]>(`/missions/${sessionId}/telemetry`);
  // Tolerate an engine older than this build rather than crashing a page on a
  // field it has not heard of.
  return frames.map((frame) => ({ ...frame, candidates: frame.candidates ?? [] }));
};

export const getDecisions = (sessionId: string) =>
  request<Decision[]>(`/missions/${sessionId}/decisions`);

export const getBelief = (sessionId: string, index: number) =>
  request<BeliefSnapshot>(`/missions/${sessionId}/belief?index=${index}`);

export const getFailures = (planner: string, condition: string) =>
  request<FailuresPayload>(
    `/failures?planner=${encodeURIComponent(planner)}&condition=${encodeURIComponent(condition)}`,
  );

export const getResults = (name = "exonaut_main") =>
  request<ResultsPayload>(`/results?name=${encodeURIComponent(name)}`);

export const getAvailableResults = () => request<string[]>("/results/available");

export const getProbe = (sessionId: string, row: number, col: number, index: number) =>
  request<ProbePayload>(`/missions/${sessionId}/probe?row=${row}&col=${col}&index=${index}`);

export const getModelConstants = () => request<ModelConstants>("/model-constants");

export const getPairedReplay = (condition: string, seed: number) =>
  request<PairedReplay>(
    `/results/paired-replay?condition=${encodeURIComponent(condition)}&seed=${seed}`,
  );

export const getDemoMission = () => request<DemoMission>("/demo-mission");

/** Live telemetry socket. Returns a disposer. */
export function openTelemetrySocket(
  sessionId: string,
  handlers: {
    onSummary?: (summary: MissionSummary) => void;
    onFrame?: (frame: TelemetryFrame) => void;
    onComplete?: (termination: string) => void;
    onError?: (message: string) => void;
  },
): { close: () => void; send: (message: object) => void } {
  const url = `${API_BASE.replace(/^http/, "ws")}/ws/telemetry/${sessionId}`;
  const socket = new WebSocket(url);

  socket.onmessage = (event) => {
    const message = JSON.parse(event.data as string);
    if (message.type === "summary") handlers.onSummary?.(message.data);
    else if (message.type === "frame") handlers.onFrame?.(message.data);
    else if (message.type === "complete") handlers.onComplete?.(message.termination);
    else if (message.type === "error") handlers.onError?.(message.message);
  };
  socket.onerror = () => handlers.onError?.("telemetry socket error");

  return {
    close: () => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ action: "stop" }));
      socket.close();
    },
    send: (message: object) => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
    },
  };
}

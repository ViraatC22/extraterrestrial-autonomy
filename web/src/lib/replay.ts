/**
 * Mission replay events, derived only from what the engine recorded.
 *
 * Every event here corresponds to a change in the recorded frames or decisions
 * - nothing is narrated that the mission did not actually do. "Terrain model
 * updated" fires only when the rover's recorded class belief actually moved,
 * so it never appears for a fixed planner.
 */

import { CLASS_NAMES } from "./palette";
import type { Decision, MissionSummary, TelemetryFrame } from "./types";

export type EventKind =
  | "landed"
  | "target_selected"
  | "replanned"
  | "slip"
  | "severe_slip"
  | "model_update"
  | "target_reached"
  | "return"
  | "intervention"
  | "hazard"
  | "end";

export interface ReplayEvent {
  frameIndex: number;
  step: number;
  kind: EventKind;
  text: string;
  tone: "good" | "warn" | "bad" | "normal" | "info";
}

export const EVENT_COLOR: Record<ReplayEvent["tone"], string> = {
  good: "#3ec9a7",
  warn: "#e8c05a",
  bad: "#e8614d",
  normal: "#9aa8bb",
  info: "#9aa8ff",
};

/** A class belief must move this much between frames to count as an update. */
const BELIEF_EPSILON = 0.005;

export function buildReplayEvents(
  frames: TelemetryFrame[],
  decisions: Decision[],
  summary: MissionSummary | null,
): ReplayEvent[] {
  const events: ReplayEvent[] = [];
  if (!frames.length) return events;
  const push = (i: number, kind: EventKind, text: string, tone: ReplayEvent["tone"]) =>
    events.push({ frameIndex: i, step: frames[i].step, kind, text, tone });

  push(0, "landed", "Mission start at lander", "normal");
  let lastGoal = "";
  let lastDecision = -1;

  frames.forEach((f, i) => {
    const prev = i > 0 ? frames[i - 1] : null;

    if (f.decision_index !== lastDecision && f.decision_index >= 0) {
      const d = decisions[f.decision_index];
      const goal = f.goal ? `${f.goal[0]},${f.goal[1]}` : "";
      if (d && d.reason === "pursue_target" && goal !== lastGoal) {
        const chosen = d.candidates.find((c) => c.selected);
        const label = chosen ? `TGT ${String(chosen.target_id).padStart(2, "0")}` : "target";
        push(i, "target_selected", `${label} selected (P(fail) ${chosen?.p_failure?.toFixed(3) ?? "—"})`, "info");
      } else if (d && goal === lastGoal && lastDecision >= 0) {
        push(i, "replanned", "Route replanned", "normal");
      }
      lastGoal = goal;
      lastDecision = f.decision_index;
    }

    if (f.reason === "slip_no_progress") {
      push(i, "severe_slip", `Severe slip ${f.slip.toFixed(2)} — no progress`, "bad");
    } else if (f.slip >= 0.5 && f.moved) {
      push(i, "slip", `High wheel slip ${f.slip.toFixed(2)}`, "warn");
    }

    if (prev) {
      const moved = Object.keys(f.belief)
        .map((k) => ({ k: Number(k), from: prev.belief[k], to: f.belief[k] }))
        .filter((b) => b.from !== undefined && Math.abs(b.to - b.from) > BELIEF_EPSILON);
      if (moved.length) {
        const big = moved.sort((a, b) => Math.abs(b.to - b.from) - Math.abs(a.to - a.from))[0];
        push(
          i,
          "model_update",
          `Terrain model updated: ${CLASS_NAMES[big.k]} slip ${big.from.toFixed(2)} → ${big.to.toFixed(2)}`,
          "info",
        );
      }
      if (f.targets_visited > prev.targets_visited) {
        push(i, "target_reached", `Science target reached (${f.targets_visited} total)`, "good");
      }
      if (f.returning && !prev.returning) push(i, "return", "Return to lander initiated", "warn");
      if (f.interventions > prev.interventions) {
        push(i, "intervention", "No believable route — ground intervention requested", "warn");
      }
    }
    if (f.reason === "hazard_refused") push(i, "hazard", "Hazard refused by onboard check", "warn");
  });

  if (summary) {
    const last = frames.length - 1;
    push(
      last,
      "end",
      summary.success
        ? `Mission ended: returned safely, science ${(summary.science_fraction * 100).toFixed(0)}%`
        : `Mission ended: ${summary.termination.replace("_", " ")}`,
      summary.success ? "good" : "bad",
    );
  }
  return events;
}

/** The most recent event at or before a frame, for captions. */
export function latestEvent(events: ReplayEvent[], frameIndex: number): ReplayEvent | null {
  let found: ReplayEvent | null = null;
  for (const e of events) {
    if (e.frameIndex > frameIndex) break;
    if (e.kind !== "slip") found = e;
  }
  return found;
}

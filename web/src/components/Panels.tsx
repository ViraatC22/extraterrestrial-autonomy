"use client";

/**
 * Telemetry surfaces. Aerospace operations panel, not a SaaS dashboard:
 * monospaced numerics, quiet chrome, one accent colour reserved for things
 * that actually need attention.
 */

import clsx from "clsx";
import type { ReactNode } from "react";

import { CLASS_NAMES, UI } from "@/lib/palette";
import type { MissionSummary, TelemetryFrame } from "@/lib/types";

export function Panel({
  title,
  children,
  className,
  right,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  right?: ReactNode;
}) {
  return (
    <section
      className={clsx(
        "rounded-sm border border-white/10 bg-[#10141c]/80 backdrop-blur-sm",
        className,
      )}
    >
      <header className="flex items-center justify-between border-b border-white/10 px-3 py-1.5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-slate-400">
          {title}
        </h2>
        {right}
      </header>
      <div className="p-3">{children}</div>
    </section>
  );
}

export function Readout({
  label,
  value,
  unit,
  tone = "normal",
}: {
  label: string;
  value: string | number;
  unit?: string;
  tone?: "normal" | "good" | "warn" | "bad" | "accent";
}) {
  const color =
    tone === "good"
      ? "text-emerald-300"
      : tone === "warn"
        ? "text-amber-300"
        : tone === "bad"
          ? "text-rose-400"
          : tone === "accent"
            ? "text-orange-400"
            : "text-slate-100";
  return (
    <div className="flex items-baseline justify-between gap-3 py-[3px]">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">
        {label}
      </span>
      <span className={clsx("font-mono text-[13px] tabular-nums", color)}>
        {value}
        {unit ? <span className="ml-1 text-[10px] text-slate-500">{unit}</span> : null}
      </span>
    </div>
  );
}

export function Bar({
  value,
  tone = "accent",
}: {
  value: number;
  tone?: "accent" | "good" | "warn" | "bad";
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const color =
    tone === "good" ? UI.good : tone === "warn" ? UI.warn : tone === "bad" ? UI.bad : UI.accent;
  return (
    <div className="h-[6px] w-full overflow-hidden rounded-sm bg-white/[0.06]">
      <div
        className="h-full transition-[width] duration-300 ease-out"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  );
}

export function RoverStatus({ frame }: { frame: TelemetryFrame | null }) {
  if (!frame) return <p className="font-mono text-xs text-slate-500">awaiting telemetry…</p>;
  const batteryTone =
    frame.charge_fraction > 0.5 ? "good" : frame.charge_fraction > 0.22 ? "warn" : "bad";
  return (
    <div className="space-y-2">
      <div>
        <Readout
          label="Energy"
          value={`${(frame.charge_fraction * 100).toFixed(0)}%`}
          tone={batteryTone}
        />
        <Bar value={frame.charge_fraction} tone={batteryTone} />
      </div>
      <Readout label="Charge" value={frame.charge.toFixed(1)} unit="Wh" />
      <Readout label="Position" value={`${frame.row}, ${frame.col}`} />
      <Readout
        label="Wheel slip"
        value={frame.slip.toFixed(3)}
        tone={frame.slip > 0.8 ? "bad" : frame.slip > 0.5 ? "warn" : "normal"}
      />
      <Readout label="Science" value={frame.science.toFixed(2)} />
      <Readout label="Targets" value={frame.targets_visited} />
      <Readout
        label="Interventions"
        value={frame.interventions}
        tone={frame.interventions > 0 ? "warn" : "normal"}
      />
    </div>
  );
}

export function AutonomyPanel({
  frame,
  plannerLabel,
  adaptive,
}: {
  frame: TelemetryFrame | null;
  plannerLabel: string;
  adaptive: boolean;
}) {
  if (!frame) return <p className="font-mono text-xs text-slate-500">idle</p>;
  const decision = frame.returning ? "RETURN TO LANDER" : "PURSUE TARGET";
  const cause =
    frame.reason === "slip_no_progress"
      ? "Severe slip — no forward progress. Replanning."
      : frame.reason === "hazard_refused"
        ? "Onboard hazard check refused the commanded move."
        : frame.reason === "insufficient_energy"
          ? "Insufficient energy for the commanded move."
          : frame.returning
            ? "No remaining objective fits the risk budget."
            : "Objective reachable within the risk budget.";
  return (
    <div className="space-y-2">
      <Readout label="Planner" value={plannerLabel} tone="accent" />
      <Readout label="Model" value={adaptive ? "ADAPTIVE" : "FIXED"} tone={adaptive ? "good" : "normal"} />
      <Readout label="Decision" value={decision} />
      {/* The engine computes P(failure) only when it assesses a trip to a
          target; while returning home the last assessed value carries over.
          Label it as what it is rather than as the risk of the current leg. */}
      <Readout
        label="P(fail) last trip assessed"
        value={frame.predicted_failure_prob.toFixed(3)}
        tone={frame.predicted_failure_prob > 0.2 ? "warn" : "normal"}
      />
      <Readout label="Goal" value={frame.goal ? `${frame.goal[0]}, ${frame.goal[1]}` : "—"} />
      <Readout label="Route length" value={frame.planned_path.length} unit="cells" />
      <p className="mt-2 border-t border-white/10 pt-2 font-mono text-[10px] leading-relaxed text-slate-400">
        {cause}
      </p>
    </div>
  );
}

export function BeliefPanel({
  frame,
  trueSlip,
  adaptive,
}: {
  frame: TelemetryFrame | null;
  trueSlip: Record<string, number>;
  adaptive: boolean;
}) {
  if (!frame) return <p className="font-mono text-xs text-slate-500">no belief state</p>;
  const classes = Object.keys(frame.belief)
    .map(Number)
    .sort((a, b) => a - b);
  return (
    <div className="space-y-2">
      <p className="font-mono text-[10px] leading-relaxed text-slate-400">
        {adaptive
          ? "Believed mean slip per terrain class, revised from what the wheels actually measure. The bar is belief; the tick is truth."
          : "This planner never revises its model, so belief stays at its prior regardless of what the wheels measure."}
      </p>
      {classes.map((klass) => {
        const believed = frame.belief[klass] ?? 0;
        const truth = trueSlip[String(klass)] ?? 0;
        const error = Math.abs(believed - truth);
        return (
          <div key={klass} className="space-y-1">
            <div className="flex items-baseline justify-between">
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">
                {CLASS_NAMES[klass] ?? klass}
              </span>
              <span
                className={clsx(
                  "font-mono text-[11px] tabular-nums",
                  error < 0.05 ? "text-emerald-300" : error < 0.15 ? "text-slate-200" : "text-amber-300",
                )}
              >
                {believed.toFixed(3)}
                <span className="ml-1 text-slate-600">/ {truth.toFixed(3)}</span>
              </span>
            </div>
            <div className="relative h-[6px] w-full rounded-sm bg-white/[0.06]">
              <div
                className="h-full rounded-sm transition-[width] duration-500 ease-out"
                style={{ width: `${Math.min(100, believed * 100)}%`, background: UI.route }}
              />
              <div
                className="absolute top-[-2px] h-[10px] w-[2px] bg-white/80"
                style={{ left: `${Math.min(100, truth * 100)}%` }}
                title="true mean slip"
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function EventLog({ events }: { events: { step: number; text: string; tone: string }[] }) {
  if (!events.length)
    return <p className="font-mono text-xs text-slate-500">no events logged</p>;
  return (
    <ul className="max-h-[210px] space-y-[3px] overflow-y-auto pr-1">
      {events
        .slice()
        .reverse()
        .map((event, index) => (
          <li key={`${event.step}-${index}`} className="flex gap-2 font-mono text-[10px]">
            <span className="shrink-0 text-slate-600">
              T+{String(event.step).padStart(4, "0")}
            </span>
            <span
              className={clsx(
                event.tone === "bad"
                  ? "text-rose-400"
                  : event.tone === "warn"
                    ? "text-amber-300"
                    : event.tone === "good"
                      ? "text-emerald-300"
                      : "text-slate-300",
              )}
            >
              {event.text}
            </span>
          </li>
        ))}
    </ul>
  );
}

export function MissionHeader({
  summary,
  step,
  total,
}: {
  summary: MissionSummary | null;
  step: number;
  total: number;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-[#0b0e14]/90 px-4 py-2">
      <div className="flex items-baseline gap-3">
        <span className="font-mono text-[13px] font-semibold tracking-[0.3em] text-slate-100">
          EXONAUT
        </span>
        <span className="font-mono text-[10px] tracking-[0.18em] text-slate-500">
          AUTONOMOUS EXPLORATION SYSTEM
        </span>
      </div>
      <div className="flex items-center gap-5 font-mono text-[10px] tracking-[0.14em] text-slate-400">
        {summary ? (
          <>
            <span>
              BODY <span className="text-slate-100">{summary.body.toUpperCase()}</span>
            </span>
            <span>
              SEED <span className="text-slate-100">{summary.seed}</span>
            </span>
            <span>
              STEP{" "}
              <span className="text-slate-100 tabular-nums">
                {String(step).padStart(4, "0")}/{String(total).padStart(4, "0")}
              </span>
            </span>
          </>
        ) : (
          <span>NO MISSION LOADED</span>
        )}
      </div>
    </div>
  );
}

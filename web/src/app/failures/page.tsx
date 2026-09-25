"use client";

/**
 * FAILURE ANALYSIS - how missions fail, one replayable case per failure mode.
 *
 * Counts and distributions come from the committed confirmatory results. Each
 * representative mission is chosen by a stated rule (closest to the category
 * median, ties to the lowest seed), re-run by the engine for detail, and
 * checked against its committed row before anything from it is shown.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/MapOverlays";
import { Nav } from "@/components/Nav";
import { Panel, Readout } from "@/components/Panels";
import { ApiError, getFailures } from "@/lib/api";
import { CLASS_NAMES } from "@/lib/palette";
import type { FailureCategory, FailuresPayload } from "@/lib/types";

const PLANNERS: [string, string][] = [
  ["adaptive_risk_aware_astar", "Adaptive risk-aware A*"],
  ["risk_aware_astar", "Fixed risk-aware A*"],
  ["astar", "Distance-only A*"],
  ["all", "All planners"],
];
const CONDITIONS: [string, string][] = [
  ["all_mars", "All Mars conditions"],
  ["mars_ood", "Mars (OOD)"],
  ["mars_high_uncertainty", "Mars · 1.5× dispersion"],
  ["mars_faults", "Mars · faults scheduled"],
  ["mars_comm_delay", "Mars · comm delay"],
  ["moon_id", "Moon (in-distribution)"],
  ["all", "All conditions"],
];
const TONE: Record<string, string> = {
  energy_exhausted: "#e8c05a",
  immobilized: "#e8614d",
  timeout: "#8b98ab",
  no_safe_objective: "#5ad2f2",
};

function Histogram({ cat }: { cat: FailureCategory }) {
  if (!cat.distribution || !cat.distribution.counts.length) return null;
  const { edges, counts } = cat.distribution;
  const max = Math.max(...counts, 1);
  const w = 260;
  const h = 64;
  const bw = w / counts.length;
  const lo = edges[0];
  const hi = edges[edges.length - 1];
  const mx = cat.median !== null ? ((cat.median - lo) / Math.max(hi - lo, 1e-9)) * w : null;
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h + 26}`}>
      {counts.map((c, i) => (
        <rect
          key={i}
          x={i * bw + 1}
          y={h - (c / max) * h}
          width={bw - 2}
          height={(c / max) * h}
          fill={TONE[cat.key] ?? "#8b98ab"}
          opacity={0.75}
        >
          <title>{`${edges[i].toFixed(2)}-${edges[i + 1].toFixed(2)}: ${c} missions`}</title>
        </rect>
      ))}
      {mx !== null ? (
        <line x1={mx} x2={mx} y1={0} y2={h} stroke="#ffffff" strokeDasharray="2 2" opacity={0.7} />
      ) : null}
      <text x={0} y={h + 12} fill="#8b98ab" fontSize={8} fontFamily="monospace">
        {lo.toFixed(2)}
      </text>
      <text x={w} y={h + 12} fill="#8b98ab" fontSize={8} textAnchor="end" fontFamily="monospace">
        {hi.toFixed(2)}
      </text>
      <text x={w / 2} y={h + 23} fill="#8b98ab" fontSize={8} textAnchor="middle" fontFamily="monospace">
        {cat.key_label} · dashed = median
      </text>
    </svg>
  );
}

function EnergyCompare({ expected, sd, actual }: { expected: number; sd: number | null; actual: number }) {
  const max = Math.max(expected + (sd ?? 0) * 2, actual) * 1.05;
  const pct = (v: number) => `${(v / max) * 100}%`;
  const sds = sd && sd > 0 ? (actual - expected) / sd : null;
  return (
    <div className="space-y-1">
      <div>
        <div className="mb-0.5 flex justify-between font-mono text-[9px] text-slate-400">
          <span>planner expected (round trip)</span>
          <span className="text-slate-200">
            {expected.toFixed(1)} ± {sd?.toFixed(1) ?? "—"} Wh
          </span>
        </div>
        <div className="relative h-2.5 rounded-[1px] bg-white/5">
          <div className="h-full rounded-[1px] bg-sky-400/70" style={{ width: pct(expected) }} />
          {sd ? (
            <div
              className="absolute top-0 h-full bg-sky-200/25"
              style={{ left: pct(Math.max(0, expected - 2 * sd)), width: pct(4 * sd) }}
              title="±2 s.d. of the planner's own estimate"
            />
          ) : null}
        </div>
      </div>
      <div>
        <div className="mb-0.5 flex justify-between font-mono text-[9px] text-slate-400">
          <span>actually spent, decision → mission end</span>
          <span className="text-slate-200">{actual.toFixed(1)} Wh</span>
        </div>
        <div className="h-2.5 rounded-[1px] bg-white/5">
          <div className="h-full rounded-[1px] bg-amber-400/80" style={{ width: pct(actual) }} />
        </div>
      </div>
      {sds !== null ? (
        <p className="font-mono text-[9px] text-slate-400">
          difference: {sds >= 0 ? "+" : ""}
          {sds.toFixed(1)} of the planner&apos;s own standard deviations
        </p>
      ) : null}
    </div>
  );
}

function CaseCard({ cat }: { cat: FailureCategory }) {
  const rep = cat.representative;
  return (
    <div className="flex flex-col rounded-sm border border-white/10 bg-[#0d1118]">
      <div className="flex items-baseline justify-between border-b border-white/10 px-3 py-2">
        <span className="font-mono text-[11px] tracking-[0.18em]" style={{ color: TONE[cat.key] }}>
          {cat.title.toUpperCase()}
        </span>
        <span className="font-mono text-[11px] tabular-nums text-slate-200">
          {cat.count} <span className="text-slate-500">({(cat.share * 100).toFixed(0)}%)</span>
        </span>
      </div>
      <div className="space-y-2 p-3">
        <p className="font-mono text-[9.5px] leading-relaxed text-slate-400">{cat.blurb}</p>
        <p className="font-mono text-[9px] text-slate-500">
          ended at the lander: {cat.at_lander} of {cat.count} · median ground-help requests:{" "}
          {cat.median_interventions?.toFixed(0) ?? "—"}
        </p>
        <Histogram cat={cat} />
        {rep ? (
          <>
            <div className="flex items-center justify-between border-t border-white/10 pt-2">
              <span className="font-mono text-[9px] tracking-[0.16em] text-slate-500">
                REPRESENTATIVE MISSION
              </span>
              {rep.reproduces_committed_row ? (
                <span className="font-mono text-[8.5px] text-emerald-300">✓ re-run reproduces committed row</span>
              ) : (
                <span className="font-mono text-[8.5px] text-rose-300">✕ re-run does NOT reproduce</span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-x-4">
              <Readout label="Seed" value={rep.seed} />
              <Readout label="Condition" value={rep.condition.replace("mars_", "")} />
              <Readout label="Ended" value={rep.termination.replace("_", " ")} />
              <Readout label="Step" value={rep.steps} />
              <Readout label="From lander" value={rep.final_distance_from_home.toFixed(1)} unit="m" />
              <Readout label="Science" value={`${(rep.science_fraction * 100).toFixed(0)}%`} />
              <Readout label="Energy spent" value={rep.energy_spent.toFixed(0)} unit="Wh" />
              <Readout label="Severe slips" value={rep.severe_slip_events} />
              <Readout label="Mean slip" value={rep.mean_slip.toFixed(3)} />
              <Readout label="Interventions" value={rep.interventions} />
            </div>
            {rep.last_trip &&
            rep.last_trip.expected_round_trip_energy !== null &&
            rep.last_trip.energy_spent_after_decision !== null ? (
              <div className="rounded-sm border border-white/10 bg-black/30 p-2">
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-mono text-[9px] tracking-[0.14em] text-slate-400">
                    LAST TRIP CHOSEN · T+{String(rep.last_trip.decision_step).padStart(4, "0")} · TGT{" "}
                    {String(rep.last_trip.target_id).padStart(2, "0")}
                  </span>
                  <StatusBadge status="INFERRED" />
                </div>
                <EnergyCompare
                  expected={rep.last_trip.expected_round_trip_energy}
                  sd={rep.last_trip.expected_energy_sd}
                  actual={rep.last_trip.energy_spent_after_decision}
                />
                <p className="mt-1 font-mono text-[9px] text-slate-400">
                  P(fail) at decision:{" "}
                  <span className="text-slate-200">
                    {rep.last_trip.p_failure !== null
                      ? rep.last_trip.p_failure < 1e-4
                        ? "< 0.0001"
                        : rep.last_trip.p_failure.toFixed(4)
                      : "—"}
                  </span>
                  . The spend is not the trip&apos;s cost alone: it runs to the end of the
                  mission, which may include later decisions.
                </p>
              </div>
            ) : null}
            {rep.belief_error_driven_classes.length ? (
              <div>
                <p className="mb-0.5 font-mono text-[9px] tracking-[0.14em] text-slate-500">
                  BELIEF VS TRUTH AT END (classes it drove on)
                </p>
                {rep.belief_error_driven_classes.map((b) => (
                  <div key={b.class} className="flex justify-between font-mono text-[9.5px]">
                    <span className="text-slate-400">
                      {CLASS_NAMES[b.class]} <span className="text-slate-600">n={b.n_observations}</span>
                    </span>
                    <span className="tabular-nums text-slate-200">
                      {b.believed.toFixed(3)} vs {b.truth.toFixed(3)}{" "}
                      <span className={b.error < 0 ? "text-sky-300" : "text-rose-300"}>
                        ({b.error >= 0 ? "+" : ""}
                        {b.error.toFixed(3)})
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
            {rep.faults_fired.length ? (
              <p className="font-mono text-[9px] text-amber-300">
                Faults fired:{" "}
                {rep.faults_fired.map((f) => `${f.fault.replace("_", " ")} @T+${f.step}`).join(", ")}
              </p>
            ) : (
              <p className="font-mono text-[9px] text-slate-500">No faults fired in this mission.</p>
            )}
            <Link
              href={`/?session=${encodeURIComponent(rep.session_id)}`}
              className="mt-1 block rounded-sm border border-orange-500/40 bg-orange-500/10 px-3 py-1.5 text-center font-mono text-[10px] tracking-[0.2em] text-orange-300 hover:bg-orange-500/20"
            >
              REPLAY IN MISSION CONTROL
            </Link>
            <p className="font-mono text-[8px] leading-snug text-slate-600">Chosen as the {cat.selection_rule}.</p>
          </>
        ) : (
          <p className="font-mono text-[10px] text-slate-500">No missions in this category.</p>
        )}
      </div>
    </div>
  );
}

export default function Failures() {
  const [planner, setPlanner] = useState("adaptive_risk_aware_astar");
  const [condition, setCondition] = useState("all_mars");
  const [payload, setPayload] = useState<FailuresPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getFailures(planner, condition);
        if (cancelled) return;
        setPayload(data);
        setError(null);
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof ApiError ? caught.message : "engine unreachable");
        setPayload(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [planner, condition]);

  const select = (fn: (v: string) => void) => (v: string) => {
    setLoading(true);
    fn(v);
  };

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-[#07090d]">
      <Nav />
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
        <Panel
          title="Failure analysis"
          right={
            <div className="flex gap-1">
              {[
                [planner, select(setPlanner), PLANNERS],
                [condition, select(setCondition), CONDITIONS],
              ].map(([value, onChange, options], i) => (
                <select
                  key={i}
                  value={value as string}
                  onChange={(e) => (onChange as (v: string) => void)(e.target.value)}
                  className="rounded-sm border border-white/10 bg-black/40 px-2 py-0.5 font-mono text-[10px] text-slate-200"
                >
                  {(options as [string, string][]).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
                </select>
              ))}
            </div>
          }
        >
          <p className="font-mono text-[10px] leading-relaxed text-slate-400">
            How missions in the confirmatory run ended, by failure mode. Counts come from the
            committed results. Each card&apos;s representative mission is chosen by a fixed rule,
            not by hand, and is re-run by the engine for detail. The re-run is checked against
            the committed row before anything from it is shown.
          </p>
          {payload ? (
            <p className="mt-1 font-mono text-[10px] text-slate-500">
              {payload.n_missions} missions in scope{loading ? " · loading…" : ""}
            </p>
          ) : null}
          {error ? <p className="mt-1 font-mono text-[10px] text-rose-300">{error}</p> : null}
        </Panel>

        {payload ? (
          <div className="grid gap-2 lg:grid-cols-2 2xl:grid-cols-4">
            {payload.categories.map((cat) => (
              <CaseCard key={cat.key} cat={cat} />
            ))}
          </div>
        ) : loading ? (
          <Panel title="Loading">
            <p className="font-mono text-[10px] text-slate-500">
              re-running representative missions on the engine…
            </p>
          </Panel>
        ) : null}

        <div className="grid gap-2 lg:grid-cols-2">
          <Panel title="Where the proposed method does not win">
            <p className="font-mono text-[10px] leading-relaxed text-slate-300">
              Distance-only A*, which models no terrain risk at all, had the highest Martian
              success rate in three of the four Martian conditions, while returning the least
              science. Risk-averse routing costs distance and exposure when most ground is
              hazardous, and the current objective charges nothing for either.
            </p>
          </Panel>
          <Panel title="What these cases can and cannot show">
            <p className="font-mono text-[10px] leading-relaxed text-slate-300">
              A representative case illustrates a failure mode. It is not evidence about
              <span className="text-slate-100"> why </span> a planner fails more or less often.
              The adaptive learner used here is known to be overconfident, and the fault condition
              rarely fired faults (see the research log). Energy mismatches like those above are
              consistent with that overconfidence, but a single case does not establish it.
            </p>
          </Panel>
        </div>
      </div>
    </main>
  );
}

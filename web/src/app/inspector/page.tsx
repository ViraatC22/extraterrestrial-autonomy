"use client";

/**
 * AUTONOMY INSPECTOR — why the planner chose what it chose.
 *
 * Shows every candidate the planner scored at a decision point, including the
 * ones it rejected and the constraint that rejected them. A planner that only
 * reports its winner cannot be audited: "it chose B" only becomes an
 * explanation once you can see what A scored.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/MapOverlays";
import { Nav } from "@/components/Nav";
import { Panel, Readout } from "@/components/Panels";
import { ApiError, DEFAULT_MISSION, getPlanners, getTelemetry, startMission } from "@/lib/api";
import type {
  CandidateEvaluation,
  MissionRequest,
  MissionSummary,
  PlannerInfo,
  TelemetryFrame,
} from "@/lib/types";

function CandidateCard({ candidate }: { candidate: CandidateEvaluation }) {
  const selected = candidate.selected;
  const rejected = Boolean(candidate.rejected);
  return (
    <div
      className={`rounded-sm border p-3 transition ${
        selected
          ? "border-emerald-400/50 bg-emerald-400/[0.07]"
          : rejected
            ? "border-rose-400/25 bg-rose-400/[0.04]"
            : "border-white/10 bg-white/[0.02]"
      }`}
    >
      <div className="mb-2 flex items-baseline justify-between">
        <span className="flex items-center gap-2 font-mono text-[11px] tracking-[0.16em] text-slate-200">
          TARGET {String(candidate.target_id).padStart(2, "0")}
          <StatusBadge status="INFERRED" />
        </span>
        <span
          className={`font-mono text-[9px] tracking-[0.16em] ${
            selected ? "text-emerald-300" : rejected ? "text-rose-300" : "text-slate-500"
          }`}
        >
          {selected ? "◀ SELECTED" : rejected ? "REJECTED" : "CONSIDERED"}
        </span>
      </div>

      {candidate.reachable ? (
        <>
          <Readout label="Science value" value={candidate.science_value.toFixed(2)} />
          <Readout label="Route length" value={candidate.path_cells ?? "—"} unit="cells" />
          <Readout
            label="Energy cost"
            value={candidate.expected_energy?.toFixed(1) ?? "—"}
            unit="Wh"
          />
          <Readout
            label="Energy uncertainty"
            value={`± ${candidate.energy_sd?.toFixed(1) ?? "—"}`}
            unit="Wh"
          />
          <Readout
            label="Solar credit"
            value={candidate.expected_solar_income?.toFixed(1) ?? "—"}
            unit="Wh"
          />
          <div className="my-2 border-t border-white/10" />
          <Readout
            label="P(fail) terrain"
            value={candidate.p_terrain?.toFixed(4) ?? "—"}
            tone={(candidate.p_terrain ?? 0) > 0.1 ? "warn" : "normal"}
          />
          <Readout
            label="P(fail) energy"
            value={candidate.p_energy?.toFixed(4) ?? "—"}
            tone={(candidate.p_energy ?? 0) > 0.1 ? "warn" : "normal"}
          />
          <Readout
            label="P(fail) total"
            value={candidate.p_failure?.toFixed(4) ?? "—"}
            tone={rejected ? "bad" : "normal"}
          />
          <div className="my-2 border-t border-white/10" />
          <Readout
            label="Utility (value / energy)"
            value={candidate.utility?.toFixed(5) ?? "—"}
            tone={selected ? "good" : "accent"}
          />
        </>
      ) : (
        <p className="font-mono text-[10px] text-slate-500">no believed route to this target</p>
      )}

      {candidate.rejected ? (
        <p className="mt-2 border-t border-white/10 pt-2 font-mono text-[9px] leading-relaxed text-rose-300">
          {candidate.rejected}
        </p>
      ) : null}
    </div>
  );
}

/**
 * The decision rule, stated once, and every candidate checked against the
 * risk budget. Explains the choice before the reader reaches the cards.
 */
function RiskBudgetCheck({
  candidates,
  riskBudget,
  viewHref,
}: {
  candidates: CandidateEvaluation[];
  riskBudget: number;
  viewHref: string | null;
}) {
  const top = Math.max(riskBudget * 1.6, ...candidates.map((c) => c.p_failure ?? 0), 1e-6);
  return (
    <Panel
      title="Decision rule"
      right={
        viewHref ? (
          <Link
            href={viewHref}
            className="rounded-sm border border-orange-500/40 bg-orange-500/10 px-2 py-0.5 font-mono text-[9px] tracking-[0.16em] text-orange-300 hover:bg-orange-500/20"
          >
            VIEW THESE ROUTES IN 3D
          </Link>
        ) : null
      }
    >
      <div className="grid gap-4 md:grid-cols-[1fr_1.4fr]">
        <div className="font-mono text-[11px] leading-relaxed text-slate-300">
          <p>
            choose the target with the largest
            <span className="mx-1 text-orange-300">science value ÷ expected energy</span>
          </p>
          <p className="mt-1">
            subject to <span className="text-slate-100">P(fail) ≤ ε = {riskBudget.toFixed(2)}</span>
          </p>
          <p className="mt-2 text-[9px] text-slate-500">
            P(fail) combines terrain risk (embedding) and energy risk (battery below reserve) over the
            full round trip, from the rover&apos;s belief, not from truth.
          </p>
        </div>
        <div className="space-y-1">
          {candidates.map((c) => {
            const p = c.p_failure;
            const ok = c.reachable && p !== null && p <= riskBudget;
            return (
              <div key={c.target_id} className="flex items-center gap-2 font-mono text-[10px]">
                <span className="w-9 text-slate-400">T{String(c.target_id).padStart(2, "0")}</span>
                <div className="relative h-2.5 flex-1 rounded-[1px] bg-white/5">
                  {p !== null ? (
                    <div
                      className={`h-full rounded-[1px] ${ok ? "bg-emerald-400/70" : "bg-rose-400/80"}`}
                      style={{ width: `${Math.min(100, (p / top) * 100)}%` }}
                    />
                  ) : null}
                  <div
                    className="absolute top-[-3px] h-[16px] w-[2px] bg-white/70"
                    style={{ left: `${(riskBudget / top) * 100}%` }}
                    title={`risk budget ε = ${riskBudget}`}
                  />
                </div>
                <span className="w-16 text-right tabular-nums text-slate-200">
                  {p !== null ? p.toFixed(3) : "—"}
                </span>
                <span className={`w-40 ${ok ? "text-emerald-300" : "text-rose-300"}`}>
                  {!c.reachable
                    ? "✕ no believed route"
                    : ok
                      ? c.selected
                        ? "✓ within budget · CHOSEN"
                        : "✓ within budget"
                      : "✕ exceeds risk limit"}
                </span>
              </div>
            );
          })}
          <p className="pt-1 font-mono text-[8.5px] text-slate-500">white line = risk budget ε</p>
        </div>
      </div>
    </Panel>
  );
}

export default function Inspector() {
  const [planners, setPlanners] = useState<PlannerInfo[]>([]);
  const [request, setRequest] = useState<MissionRequest>({
    ...DEFAULT_MISSION,
    size: 48,
    max_steps: 400,
  });
  const [frames, setFrames] = useState<TelemetryFrame[]>([]);
  const [summary, setSummary] = useState<MissionSummary | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [decisionIndex, setDecisionIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getPlanners().then(setPlanners).catch(() => undefined);
  }, []);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const started = await startMission(request);
      const telemetry = await getTelemetry(started.session_id);
      setSummary(started.summary);
      setSessionId(started.session_id);
      setFrames(telemetry);
      setDecisionIndex(0);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "engine unreachable");
    } finally {
      setBusy(false);
    }
  }, [request]);

  /** Frames where the planner actually re-evaluated its options. */
  const decisions = useMemo(() => {
    const seen: TelemetryFrame[] = [];
    let previousKey = "";
    frames.forEach((frame) => {
      if (!frame.candidates?.length) return;
      const key = frame.candidates
        .map((c) => `${c.target_id}:${c.selected}:${c.rejected ?? ""}`)
        .join("|");
      if (key !== previousKey) {
        seen.push(frame);
        previousKey = key;
      }
    });
    return seen;
  }, [frames]);

  const decision = decisions[decisionIndex] ?? null;
  const plannerInfo = planners.find((p) => p.name === request.planner);

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-[#07090d]">
      <Nav />
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 p-2 lg:grid-cols-[250px_1fr]">
        <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
          <Panel title="Mission">
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
                  <option value="mars">MARS</option>
                  <option value="moon">MOON</option>
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
              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">
                  Seed
                </span>
                <input
                  type="number"
                  value={request.seed}
                  onChange={(e) => setRequest({ ...request, seed: Number(e.target.value) })}
                  className="mt-1 w-full rounded-sm border border-white/10 bg-black/40 px-2 py-1 font-mono text-[11px] text-slate-200"
                />
              </label>
              <label className="block">
                <span className="flex items-baseline justify-between font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">
                  Risk budget ε<span className="text-slate-300">{request.risk_budget}</span>
                </span>
                <input
                  type="range"
                  min={0.02}
                  max={0.6}
                  step={0.02}
                  value={request.risk_budget}
                  onChange={(e) =>
                    setRequest({ ...request, risk_budget: Number(e.target.value) })
                  }
                  className="mt-1 w-full accent-orange-500"
                />
              </label>
              <button
                onClick={load}
                disabled={busy}
                className="w-full rounded-sm border border-orange-500/40 bg-orange-500/10 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.2em] text-orange-300 hover:bg-orange-500/20 disabled:opacity-40"
              >
                {busy ? "running…" : "evaluate"}
              </button>
              {error ? (
                <p className="rounded-sm border border-rose-500/30 bg-rose-500/10 p-2 font-mono text-[9px] text-rose-300">
                  {error}
                </p>
              ) : null}
            </div>
          </Panel>

          <Panel title="How the score works">
            <p className="font-mono text-[9px] leading-relaxed text-slate-400">
              For each remaining target the planner plans a full round trip on its
              believed map, then estimates the probability that trip ends the
              mission — from terrain (embedding in loose ground) and from energy
              (running the battery below reserve).
            </p>
            <p className="mt-2 font-mono text-[9px] leading-relaxed text-slate-400">
              Any candidate whose total P(failure) exceeds the risk budget ε is
              discarded outright. Among what survives, the planner takes the best
              science value per unit of energy.
            </p>
            <p className="mt-2 font-mono text-[9px] leading-relaxed text-slate-500">
              So the winner is not always the cheapest or the safest — it is the
              best trade, subject to a hard safety constraint.
            </p>
          </Panel>
        </div>

        <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
          {decision ? (
            <>
              <Panel
                title={`Decision point ${decisionIndex + 1} of ${decisions.length}`}
                right={
                  <div className="flex gap-1">
                    <button
                      onClick={() => setDecisionIndex((i) => Math.max(0, i - 1))}
                      disabled={decisionIndex === 0}
                      className="rounded-sm border border-white/15 px-2 py-0.5 font-mono text-[9px] text-slate-300 disabled:opacity-30"
                    >
                      PREV
                    </button>
                    <button
                      onClick={() =>
                        setDecisionIndex((i) => Math.min(decisions.length - 1, i + 1))
                      }
                      disabled={decisionIndex >= decisions.length - 1}
                      className="rounded-sm border border-white/15 px-2 py-0.5 font-mono text-[9px] text-slate-300 disabled:opacity-30"
                    >
                      NEXT
                    </button>
                  </div>
                }
              >
                <div className="grid grid-cols-2 gap-x-6 md:grid-cols-4">
                  <Readout label="Step" value={`T+${String(decision.step).padStart(4, "0")}`} />
                  <Readout label="Rover at" value={`${decision.row}, ${decision.col}`} />
                  <Readout
                    label="Battery"
                    value={`${(decision.charge_fraction * 100).toFixed(0)}%`}
                    tone={decision.charge_fraction < 0.3 ? "warn" : "normal"}
                  />
                  <Readout
                    label="Verdict"
                    value={decision.returning ? "RETURN HOME" : "PURSUE"}
                    tone={decision.returning ? "warn" : "good"}
                  />
                </div>
                {decision.decision_reason ? (
                  <p className="mt-2 border-t border-white/10 pt-2 font-mono text-[10px] text-slate-400">
                    reason: <span className="text-slate-200">{decision.decision_reason}</span>
                  </p>
                ) : null}
                {plannerInfo ? (
                  <p className="mt-1 font-mono text-[9px] text-slate-500">
                    {plannerInfo.label} · model{" "}
                    {plannerInfo.adaptive ? "ADAPTIVE" : "FIXED"}
                  </p>
                ) : null}
              </Panel>

              <RiskBudgetCheck
                candidates={decision.candidates}
                riskBudget={request.risk_budget}
                viewHref={
                  sessionId
                    ? `/?session=${encodeURIComponent(sessionId)}&frame=${frames.indexOf(decision)}&camera=planner`
                    : null
                }
              />

              <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                {decision.candidates.map((candidate) => (
                  <CandidateCard key={candidate.target_id} candidate={candidate} />
                ))}
              </div>

              {summary ? (
                <Panel title="Mission outcome">
                  <div className="grid grid-cols-2 gap-x-6 md:grid-cols-4">
                    <Readout
                      label="Ended"
                      value={summary.success ? "RETURNED SAFELY" : summary.termination.replace("_", " ").toUpperCase()}
                      tone={summary.success ? "good" : "bad"}
                    />
                    <Readout
                      label="Science"
                      value={`${(summary.science_fraction * 100).toFixed(0)}%`}
                    />
                    <Readout label="Energy" value={summary.energy_spent.toFixed(0)} unit="Wh" />
                    <Readout label="Decisions" value={decisions.length} />
                  </div>
                </Panel>
              ) : null}
            </>
          ) : (
            <Panel title="Autonomy Inspector">
              <p className="font-mono text-[11px] text-slate-500">
                Run an evaluation to see every candidate the planner scored, what it
                rejected, and why.
              </p>
            </Panel>
          )}
        </div>
      </div>
    </main>
  );
}

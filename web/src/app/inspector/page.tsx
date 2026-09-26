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
import { ApiError, DEFAULT_MISSION, getDecisions, getPlanners, getTelemetry, startMission } from "@/lib/api";
import type {
  CandidateRoute,
  Decision,
  MissionRequest,
  MissionSummary,
  PlannerInfo,
  TelemetryFrame,
} from "@/lib/types";

const fmt = (v: number | null | undefined, digits: number) =>
  v === null || v === undefined ? "—" : v.toFixed(digits);

/**
 * The decision for one candidate, walked through with the engine's own
 * numbers. Nothing is computed here: utility, P(fail), the budget verdict and
 * the rank all arrive from the mission manager.
 */
function Calculation({
  candidate,
  riskBudget,
  nFeasible,
}: {
  candidate: CandidateRoute;
  riskBudget: number;
  nFeasible: number;
}) {
  const row = (label: string, value: string, note?: string) => (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-slate-500">{label}</span>
      <span className="tabular-nums text-slate-100">
        {value}
        {note ? <span className="ml-1 text-[8.5px] text-slate-500">{note}</span> : null}
      </span>
    </div>
  );
  if (!candidate.reachable) {
    return <p className="text-slate-400">No route on the rover&apos;s believed map, so nothing to score.</p>;
  }
  const ok = candidate.within_budget;
  return (
    <div className="space-y-2">
      <div className="space-y-0.5">
        <p className="text-[8.5px] tracking-[0.16em] text-slate-500">1 · UTILITY</p>
        {row("science value", fmt(candidate.science_value, 2))}
        {row("expected energy", `${fmt(candidate.expected_energy, 1)} Wh`, "full round trip")}
        {row(
          "value / energy",
          `${fmt(candidate.science_value, 2)} / ${fmt(candidate.expected_energy, 1)} = ${fmt(candidate.utility, 5)}`,
        )}
        <p className="text-[8.5px] text-slate-500">utility as the engine computed it, from unrounded inputs</p>
      </div>
      <div className="space-y-0.5">
        <p className="text-[8.5px] tracking-[0.16em] text-slate-500">2 · RISK</p>
        {row("P(fail) terrain", fmt(candidate.p_terrain, 4), "embedding, from belief")}
        {row(
          "P(fail) energy",
          fmt(candidate.p_energy, 4),
          `± ${fmt(candidate.energy_sd, 1)} Wh; solar credit ${fmt(candidate.expected_solar_income, 1)} Wh`,
        )}
        {row("P(fail) total", fmt(candidate.p_failure, 4), "1 − (1 − terrain)(1 − energy)")}
      </div>
      <div className="space-y-0.5">
        <p className="text-[8.5px] tracking-[0.16em] text-slate-500">3 · CONSTRAINT</p>
        {row("risk budget ε", fmt(riskBudget, 4))}
        <p className={ok ? "text-emerald-300" : "text-rose-300"}>
          {fmt(candidate.p_failure, 4)} {ok ? "≤" : ">"} {fmt(riskBudget, 4)} {ok ? "✓ within budget" : "✕ exceeds budget"}
        </p>
      </div>
      <div className="border-t border-white/10 pt-1.5">
        <p className="text-[8.5px] tracking-[0.16em] text-slate-500">4 · DECISION</p>
        <p className={candidate.selected ? "text-emerald-300" : ok ? "text-slate-200" : "text-rose-300"}>
          {candidate.selected
            ? `Highest utility of ${nFeasible} feasible candidate${nFeasible === 1 ? "" : "s"} → selected.`
            : ok
              ? `Feasible, but ranked ${candidate.feasible_rank} of ${nFeasible} by utility → not selected.`
              : "Removed before utility is compared → not selected."}
        </p>
      </div>
    </div>
  );
}

function CandidateCard({
  candidate,
  riskBudget,
  nFeasible,
}: {
  candidate: CandidateRoute;
  riskBudget: number;
  nFeasible: number;
}) {
  const selected = candidate.selected;
  const rejected = !candidate.within_budget;
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
          {selected ? "◀ SELECTED" : rejected ? "REJECTED" : `FEASIBLE · RANK ${candidate.feasible_rank}`}
        </span>
      </div>

      {candidate.reachable ? (
        <>
          <Readout label="Science value" value={candidate.science_value.toFixed(2)} />
          <Readout label="Route length" value={candidate.path_cells ?? "—"} unit="cells" />
          <Readout label="Energy cost" value={fmt(candidate.expected_energy, 1)} unit="Wh" />
          <Readout label="P(fail) total" value={fmt(candidate.p_failure, 4)} tone={rejected ? "bad" : "normal"} />
          <Readout
            label="Utility (value / energy)"
            value={fmt(candidate.utility, 5)}
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

      <details className="group mt-2 border-t border-white/10 pt-1.5">
        <summary className="cursor-pointer select-none font-mono text-[9px] tracking-[0.18em] text-orange-300 hover:text-orange-200">
          <span className="group-open:hidden">SHOW CALCULATION</span>
          <span className="hidden group-open:inline">HIDE CALCULATION</span>
        </summary>
        <div className="mt-1.5 font-mono text-[10px]">
          <Calculation candidate={candidate} riskBudget={riskBudget} nFeasible={nFeasible} />
        </div>
      </details>
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
  candidates: CandidateRoute[];
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
            const ok = c.within_budget; // the engine's verdict, not re-derived
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
  const [allDecisions, setAllDecisions] = useState<Decision[]>([]);
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
      const [telemetry, decisionList] = await Promise.all([
        getTelemetry(started.session_id),
        getDecisions(started.session_id),
      ]);
      setSummary(started.summary);
      setSessionId(started.session_id);
      setFrames(telemetry);
      setAllDecisions(decisionList);
      setDecisionIndex(0);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "engine unreachable");
    } finally {
      setBusy(false);
    }
  }, [request]);

  /**
   * Decisions where candidates were scored, skipping replans whose verdicts
   * did not change (same targets, same selection, same budget verdicts).
   */
  const decisions = useMemo(() => {
    const seen: Decision[] = [];
    let previousKey = "";
    allDecisions.forEach((d) => {
      if (!d.candidates.length) return;
      const key = d.candidates.map((c) => `${c.target_id}:${c.selected}:${c.within_budget}`).join("|");
      if (key !== previousKey) {
        seen.push(d);
        previousKey = key;
      }
    });
    return seen;
  }, [allDecisions]);

  const decision = decisions[decisionIndex] ?? null;
  const plannerInfo = planners.find((p) => p.name === request.planner);
  const firstFrame = decision ? frames.findIndex((f) => f.decision_index === decision.index) : -1;
  const nFeasible = decision ? decision.candidates.filter((c) => c.within_budget).length : 0;
  const verdict =
    decision?.reason === "pursue_target"
      ? "PURSUE"
      : decision?.reason === "no_target_within_budget"
        ? "RETURN HOME"
        : (decision?.reason ?? "—").replace(/_/g, " ").toUpperCase();

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
                    value={verdict}
                    tone={decision.reason === "pursue_target" ? "good" : "warn"}
                  />
                </div>
                {decision.reason ? (
                  <p className="mt-2 border-t border-white/10 pt-2 font-mono text-[10px] text-slate-400">
                    reason: <span className="text-slate-200">{decision.reason}</span>
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
                riskBudget={decision.risk_budget}
                viewHref={
                  sessionId && firstFrame >= 0
                    ? `/?session=${encodeURIComponent(sessionId)}&frame=${firstFrame}&camera=planner`
                    : null
                }
              />

              <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                {decision.candidates.map((candidate) => (
                  <CandidateCard
                    key={candidate.target_id}
                    candidate={candidate}
                    riskBudget={decision.risk_budget}
                    nFeasible={nFeasible}
                  />
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

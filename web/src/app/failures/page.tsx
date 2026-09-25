"use client";

/**
 * FAILURE ANALYSIS — where the autonomy breaks, including where ours loses.
 *
 * A comparison that only shows wins is not evidence. This page leads with the
 * seeds where the proposed method lost to the control.
 */

import { useEffect, useMemo, useState } from "react";

import { Nav } from "@/components/Nav";
import { Panel, Readout } from "@/components/Panels";
import { ApiError, getResults } from "@/lib/api";
import type { ResultsPayload } from "@/lib/types";

const CONDITION_LABELS: Record<string, string> = {
  moon_id: "Moon (in-distribution)",
  mars_ood: "Mars (OOD)",
  mars_high_uncertainty: "Mars · 1.5× dispersion",
  mars_faults: "Mars · faults scheduled",
  mars_comm_delay: "Mars · comm delay",
};
const PLANNER_LABELS: Record<string, string> = {
  astar: "Distance-only A*",
  risk_aware_astar: "Fixed risk-aware A*",
  adaptive_risk_aware_astar: "Adaptive risk-aware A*",
};

export default function Failures() {
  const [payload, setPayload] = useState<ResultsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getResults("exonaut_main");
        if (!cancelled) setPayload(data);
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "engine unreachable");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /** Failure counts per planner, summed over conditions. */
  const byPlanner = useMemo(() => {
    if (!payload) return [];
    const totals = new Map<
      string,
      { immobilized: number; energy: number; timeout: number; n: number; success: number }
    >();
    payload.descriptive.forEach((row) => {
      const planner = row.planner as string;
      const entry =
        totals.get(planner) ?? { immobilized: 0, energy: 0, timeout: 0, n: 0, success: 0 };
      entry.immobilized += Number(row.immobilized ?? 0);
      entry.energy += Number(row.energy_exhausted ?? 0);
      entry.timeout += Number(row.timeout ?? 0);
      entry.n += Number(row.n ?? 0);
      entry.success += Number(row.success_rate ?? 0) * Number(row.n ?? 0);
      totals.set(planner, entry);
    });
    return [...totals.entries()].map(([planner, value]) => ({ planner, ...value }));
  }, [payload]);

  const worstConditions = useMemo(() => {
    if (!payload) return [];
    return [...payload.descriptive]
      .sort((a, b) => Number(a.success_rate) - Number(b.success_rate))
      .slice(0, 6);
  }, [payload]);

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-[#07090d]">
      <Nav />
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
        {error ? (
          <Panel title="Failure Analysis">
            <p className="font-mono text-[10px] text-rose-300">{error}</p>
          </Panel>
        ) : null}

        <Panel title="The failure mode that dominates">
          <p className="font-mono text-[10px] leading-relaxed text-slate-300">
            Energy exhaustion, not embedding, accounts for most Martian losses. A
            robot carrying a lunar prior underestimates slip in drift sand, and
            because locomotion cost carries a 1/(1−slip) term it therefore
            underestimates the cost of <span className="text-slate-100">every</span>{" "}
            route it considers. It commits to a trip it cannot afford and strands
            itself short of the lander.
          </p>
          <p className="mt-2 font-mono text-[10px] leading-relaxed text-slate-400">
            Correcting the slip belief corrects the energy estimate, which is why
            adaptation reduces this specific failure mode rather than improving
            everything uniformly — and why it buys survival rather than science.
          </p>
        </Panel>

        <Panel title="Failure counts by planner (all conditions)">
          <div className="overflow-x-auto">
            <table className="w-full font-mono text-[10px]">
              <thead>
                <tr className="text-slate-500">
                  {["Planner", "Missions", "Successes", "Immobilized", "Energy out", "Timeout"].map(
                    (header) => (
                      <th key={header} className="px-2 py-1 text-left font-normal tracking-[0.1em]">
                        {header}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {byPlanner.map((row) => (
                  <tr key={row.planner} className="border-t border-white/5">
                    <td className="px-2 py-1 text-slate-200">
                      {PLANNER_LABELS[row.planner] ?? row.planner}
                    </td>
                    <td className="px-2 py-1 tabular-nums text-slate-400">{row.n}</td>
                    <td className="px-2 py-1 tabular-nums text-emerald-300">
                      {Math.round(row.success)}
                    </td>
                    <td className="px-2 py-1 tabular-nums text-rose-300">{row.immobilized}</td>
                    <td className="px-2 py-1 tabular-nums text-amber-300">{row.energy}</td>
                    <td className="px-2 py-1 tabular-nums text-slate-400">{row.timeout}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Where the proposed method does not win">
          <p className="mb-2 font-mono text-[10px] leading-relaxed text-slate-300">
            Distance-only A* — which models no terrain risk at all — achieved the
            highest Martian success rate in three of four conditions, while
            returning the least science. Risk-averse routing is expensive when
            nearly all ground is hazardous: detours cost distance and exposure,
            and the current objective charges nothing for either.
          </p>
          <p className="font-mono text-[10px] leading-relaxed text-amber-300/90">
            This is a limitation of the risk formulation, not an incidental
            result, and it is reported in the paper as such.
          </p>
        </Panel>

        <Panel title="Hardest conditions (lowest success rates)">
          <div className="overflow-x-auto">
            <table className="w-full font-mono text-[10px]">
              <thead>
                <tr className="text-slate-500">
                  {["Condition", "Planner", "Success", "Science", "Immob.", "Energy out"].map(
                    (header) => (
                      <th key={header} className="px-2 py-1 text-left font-normal tracking-[0.1em]">
                        {header}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {worstConditions.map((row, index) => (
                  <tr key={index} className="border-t border-white/5">
                    <td className="px-2 py-1 text-slate-400">
                      {CONDITION_LABELS[row.condition as string] ?? row.condition}
                    </td>
                    <td className="px-2 py-1 text-slate-200">
                      {PLANNER_LABELS[row.planner as string] ?? row.planner}
                    </td>
                    <td className="px-2 py-1 tabular-nums text-rose-300">
                      {Number(row.success_rate).toFixed(2)}
                    </td>
                    <td className="px-2 py-1 tabular-nums text-slate-300">
                      {Number(row.science_fraction).toFixed(3)}
                    </td>
                    <td className="px-2 py-1 tabular-nums text-rose-300/80">
                      {String(row.immobilized)}
                    </td>
                    <td className="px-2 py-1 tabular-nums text-amber-300/80">
                      {String(row.energy_exhausted)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        {payload ? (
          <Panel title="Honest summary">
            <div className="grid grid-cols-2 gap-x-8 md:grid-cols-4">
              <Readout label="Missions analysed" value={payload.n_missions} />
              <Readout label="Contrasts tested" value={payload.primary.length} />
              <Readout
                label="Surviving Holm"
                value={payload.primary.filter((r) => r.significant).length}
                tone="accent"
              />
              <Readout label="Primary hypothesis" value="NOT SUPPORTED" tone="bad" />
            </div>
          </Panel>
        ) : null}
      </div>
    </main>
  );
}

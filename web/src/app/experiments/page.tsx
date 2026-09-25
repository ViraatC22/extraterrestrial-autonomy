"use client";

/**
 * EXPERIMENTS — the confirmatory statistics, read from committed results.
 *
 * Nothing on this page is computed in the browser. The numbers come from the
 * same files the paper is generated from, so the interface and the paper
 * cannot disagree.
 */

import { useEffect, useState } from "react";

import { Nav } from "@/components/Nav";
import { Panel, Readout } from "@/components/Panels";
import { ApiError, getAvailableResults, getResults } from "@/lib/api";
import type { ResultsPayload } from "@/lib/types";

const CONDITION_LABELS: Record<string, string> = {
  moon_id: "Moon (in-distribution)",
  mars_ood: "Mars (out-of-distribution)",
  mars_high_uncertainty: "Mars · 1.5× slip dispersion",
  mars_faults: "Mars · hardware faults",
  mars_comm_delay: "Mars · 20-step comm delay",
};
const PLANNER_LABELS: Record<string, string> = {
  astar: "Distance-only A*",
  dijkstra: "Dijkstra",
  dstar_lite: "D* Lite",
  risk_aware_astar: "Fixed risk-aware A*",
  adaptive_risk_aware_astar: "Adaptive risk-aware A*",
};

function num(value: unknown, digits = 3): string {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}

export default function Experiments() {
  const [names, setNames] = useState<string[]>([]);
  const [selected, setSelected] = useState("exonaut_main");
  const [payload, setPayload] = useState<ResultsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAvailableResults()
      .then((available) => {
        setNames(available);
        if (!available.includes("exonaut_main") && available.length) setSelected(available[0]);
      })
      .catch(() => undefined);
  }, []);

  // The `cancelled` flag is not ceremony: without it, switching result sets
  // while a fetch is in flight lets a slower earlier response overwrite a
  // newer one, so the table can end up showing a different dataset than the
  // selector says.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getResults(selected);
        if (cancelled) return;
        setPayload(data);
        setError(null);
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof ApiError ? caught.message : "engine unreachable");
        setPayload(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const metadata = (payload?.metadata ?? {}) as Record<string, never>;
  const git = (metadata.git ?? {}) as Record<string, string | boolean>;
  const quarantined = (metadata.quarantined_seeds ?? {}) as Record<string, number[]>;

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-[#07090d]">
      <Nav />
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
        <Panel
          title="Result set"
          right={
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="rounded-sm border border-white/10 bg-black/40 px-2 py-0.5 font-mono text-[10px] text-slate-200"
            >
              {names.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          }
        >
          {error ? (
            <p className="rounded-sm border border-rose-500/30 bg-rose-500/10 p-2 font-mono text-[10px] text-rose-300">
              {error}
            </p>
          ) : payload ? (
            <>
              <div className="grid grid-cols-2 gap-x-8 md:grid-cols-4">
                <Readout label="Missions" value={payload.n_missions} />
                <Readout
                  label="Seeds / condition"
                  value={String(metadata.n_seeds_per_condition ?? "—")}
                />
                <Readout
                  label="Commit"
                  value={String(git.commit ?? "—").slice(0, 10)}
                />
                <Readout
                  label="Split checksum"
                  value={String(metadata.seed_split_checksum ?? "—").slice(0, 10)}
                />
              </div>
              {Object.keys(quarantined).length ? (
                <p className="mt-2 border-t border-white/10 pt-2 font-mono text-[9px] leading-relaxed text-amber-300/80">
                  Quarantined seeds excluded from this run:{" "}
                  {Object.entries(quarantined)
                    .map(([split, seeds]) => `${split} ${seeds.join(", ")}`)
                    .join(" · ")}
                </p>
              ) : null}
              {selected !== "exonaut_main" ? (
                <p className="mt-2 font-mono text-[9px] leading-relaxed text-amber-300">
                  This is not the confirmatory result set. The pilot predates the
                  defect fixes recorded in docs/RESEARCH_LOG.md and is kept only as
                  a historical record.
                </p>
              ) : null}
            </>
          ) : (
            <p className="font-mono text-[10px] text-slate-500">loading…</p>
          )}
        </Panel>

        {payload ? (
          <>
            <Panel title="Outcomes by condition">
              <div className="overflow-x-auto">
                <table className="w-full font-mono text-[10px]">
                  <thead>
                    <tr className="text-slate-500">
                      {["Condition", "Planner", "n", "Success", "Science", "Immob.", "Energy out"].map(
                        (header) => (
                          <th key={header} className="px-2 py-1 text-left font-normal tracking-[0.1em]">
                            {header}
                          </th>
                        ),
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {payload.descriptive.map((row, index) => {
                      const adaptive = row.planner === "adaptive_risk_aware_astar";
                      return (
                        <tr
                          key={index}
                          className={`border-t border-white/5 ${adaptive ? "bg-orange-500/[0.05]" : ""}`}
                        >
                          <td className="px-2 py-1 text-slate-400">
                            {CONDITION_LABELS[row.condition as string] ?? row.condition}
                          </td>
                          <td className="px-2 py-1 text-slate-200">
                            {PLANNER_LABELS[row.planner as string] ?? row.planner}
                          </td>
                          <td className="px-2 py-1 tabular-nums text-slate-400">{String(row.n)}</td>
                          <td className="px-2 py-1 tabular-nums text-slate-100">
                            {num(row.success_rate, 2)}
                          </td>
                          <td className="px-2 py-1 tabular-nums text-slate-100">
                            {num(row.science_fraction)}
                          </td>
                          <td className="px-2 py-1 tabular-nums text-rose-300/80">
                            {String(row.immobilized)}
                          </td>
                          <td className="px-2 py-1 tabular-nums text-amber-300/80">
                            {String(row.energy_exhausted)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Panel>

            <Panel title="Primary contrasts — adaptive vs fixed risk-aware">
              <p className="mb-2 font-mono text-[9px] leading-relaxed text-slate-400">
                Paired within condition and seed, Holm-corrected across the primary
                family. Mission success is binary and paired, so it uses McNemar&apos;s
                exact test on the seeds where the planners actually disagreed.
              </p>
              <div className="overflow-x-auto">
                <table className="w-full font-mono text-[10px]">
                  <thead>
                    <tr className="text-slate-500">
                      {["Condition", "Outcome", "Δ", "95% CI", "Test", "p (Holm)"].map((header) => (
                        <th key={header} className="px-2 py-1 text-left font-normal tracking-[0.1em]">
                          {header}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {payload.primary.map((row, index) => {
                      const significant = Boolean(row.significant);
                      const delta = row.mean_diff as number;
                      return (
                        <tr
                          key={index}
                          className={`border-t border-white/5 ${significant ? "bg-emerald-400/[0.07]" : ""}`}
                        >
                          <td className="px-2 py-1 text-slate-400">
                            {CONDITION_LABELS[row.condition as string] ?? row.condition}
                          </td>
                          <td className="px-2 py-1 text-slate-300">
                            {row.metric === "science_fraction" ? "science fraction" : "mission success"}
                          </td>
                          <td
                            className={`px-2 py-1 tabular-nums ${delta > 0 ? "text-emerald-300" : delta < 0 ? "text-rose-300" : "text-slate-400"}`}
                          >
                            {delta > 0 ? "+" : ""}
                            {num(delta)}
                          </td>
                          <td className="px-2 py-1 tabular-nums text-slate-400">
                            [{num(row.ci95_low)}, {num(row.ci95_high)}]
                          </td>
                          <td className="px-2 py-1 text-slate-500">{String(row.test)}</td>
                          <td
                            className={`px-2 py-1 tabular-nums ${significant ? "text-emerald-300" : "text-slate-400"}`}
                          >
                            {num(row.p_holm)}
                            {significant ? " ✻" : ""}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Panel>

            <div className="grid gap-2 lg:grid-cols-2">
              <Panel title="Generalization gap">
                <table className="w-full font-mono text-[10px]">
                  <tbody>
                    {payload.generalization_gap.map((row, index) => (
                      <tr key={index} className="border-t border-white/5">
                        <td className="px-2 py-1 text-slate-300">
                          {PLANNER_LABELS[row.planner as string] ?? row.planner}
                        </td>
                        <td className="px-2 py-1 tabular-nums text-slate-400">
                          {num(row.in_distribution)} → {num(row.out_of_distribution)}
                        </td>
                        <td className="px-2 py-1 tabular-nums text-slate-100">
                          G = {num(row.generalization_gap)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-2 border-t border-white/10 pt-2 font-mono text-[9px] leading-relaxed text-slate-500">
                  G is a difference, so it mechanically rewards planners that perform
                  poorly in distribution. Reported for completeness; it is not
                  informative for ranking here.
                </p>
              </Panel>

              <Panel title="Verdict against the stated hypotheses">
                <ul className="space-y-1.5 font-mono text-[9px] leading-relaxed">
                  <li className="text-emerald-300">
                    H1 supported — lunar parity between adaptive and fixed.
                  </li>
                  <li className="text-rose-300">
                    H2 not supported — Martian science fraction moved against the
                    hypothesis and Martian success was exactly tied. The
                    validation-set advantage did not replicate on held-out seeds.
                  </li>
                  <li className="text-amber-300">
                    H3 partially supported — success under injected faults rose, the
                    only contrast surviving Holm correction; adaptation won every
                    discordant seed.
                  </li>
                  <li className="text-slate-400">H4 — reported descriptively above.</li>
                </ul>
                <p className="mt-2 border-t border-white/10 pt-2 font-mono text-[9px] leading-relaxed text-slate-400">
                  Reporting a failed primary hypothesis is the point of fixing the
                  analysis plan in advance. Without frozen splits, the validation
                  figure is the one that would have been published.
                </p>
              </Panel>
            </div>
          </>
        ) : null}
      </div>
    </main>
  );
}

"use client";

/**
 * EXPERIMENTS — the confirmatory statistics, read from committed results.
 *
 * Nothing on this page is computed in the browser. The numbers come from the
 * same files the paper is generated from, so the interface and the paper
 * cannot disagree.
 */

import { useEffect, useState } from "react";

import {
  DotCIChart,
  ForestPlot,
  PLANNER_COLOR,
  PLANNER_SHORT,
  PairedScatter,
  ParetoPlot,
  SlopeChart,
  StackedBars,
} from "@/components/Charts";
import { Nav } from "@/components/Nav";
import { Panel, Readout } from "@/components/Panels";
import { ApiError, getAvailableResults, getResults } from "@/lib/api";
import type { ResultsPayload } from "@/lib/types";

const CONDITION_LABELS: Record<string, string> = {
  moon_id: "Moon (in-distribution)",
  mars_ood: "Mars (out-of-distribution)",
  mars_high_uncertainty: "Mars · 1.5× slip dispersion",
  mars_faults: "Mars · faults scheduled",
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

const PLANNER_ORDER = ["adaptive_risk_aware_astar", "risk_aware_astar", "astar"];
const CONDITION_ORDER = ["moon_id", "mars_ood", "mars_high_uncertainty", "mars_faults", "mars_comm_delay"];
const SHORT_COND: Record<string, string> = {
  moon_id: "Moon ID",
  mars_ood: "Mars OOD",
  mars_high_uncertainty: "Mars 1.5× disp.",
  mars_faults: "Mars faults sched.",
  mars_comm_delay: "Mars comm delay",
};

function ChartsSection({ payload }: { payload: ResultsPayload }) {
  const conditions = CONDITION_ORDER.filter((c) => payload.intervals.some((r) => r.condition === c));
  const [scatterCondition, setScatterCondition] = useState("mars_faults");
  const intervalsFor = (c: string) =>
    PLANNER_ORDER.map((pl) => payload.intervals.find((r) => r.condition === c && r.planner === pl)).filter(
      (r): r is NonNullable<typeof r> => Boolean(r),
    );

  const forestRows = (metric: string) =>
    CONDITION_ORDER.map((c) =>
      payload.primary.find((r) => r.condition === c && r.metric === metric),
    )
      .filter(Boolean)
      .map((r) => {
        const row = r as Record<string, number | string | boolean>;
        return {
          label: `${SHORT_COND[row.condition as string]}`,
          delta: row.mean_diff as number,
          low: row.ci95_low as number,
          high: row.ci95_high as number,
          p: row.p_holm as number,
          significant: Boolean(row.significant),
        };
      });

  const paretoPoints = payload.intervals.map((r) => ({
    key: `${r.condition}-${r.planner}`,
    label: `${SHORT_COND[r.condition]} · ${PLANNER_SHORT[r.planner]}`,
    color: PLANNER_COLOR[r.planner] ?? "#999",
    x: r.success_rate,
    xLow: r.success_ci_low,
    xHigh: r.success_ci_high,
    y: r.science_fraction,
    yLow: r.science_ci_low,
    yHigh: r.science_ci_high,
  }));

  const pairs = payload.paired_points
    .filter((p) => p.condition === scatterCondition)
    .map((p) => ({
      x: p.science_control,
      y: p.science_treatment,
      both: p.success_treatment && p.success_control,
      onlyT: p.success_treatment && !p.success_control,
      onlyC: !p.success_treatment && p.success_control,
    }));
  const scatterContrast = payload.primary.find(
    (r) => r.condition === scatterCondition && r.metric === "success",
  ) as Record<string, number> | undefined;

  const stackRows = conditions.flatMap((c) =>
    PLANNER_ORDER.map((pl) => {
      const d = payload.descriptive.find((r) => r.condition === c && r.planner === pl);
      if (!d) return null;
      const n = Number(d.n);
      return {
        label: `${SHORT_COND[c]} · ${PLANNER_SHORT[pl]}`,
        total: n,
        parts: [
          { key: "returned safely", value: Number(d.completed ?? 0), color: "#3ec9a7" },
          { key: "energy exhausted", value: Number(d.energy_exhausted ?? 0), color: "#e8c05a" },
          { key: "immobilized", value: Number(d.immobilized ?? 0), color: "#e8614d" },
          { key: "timeout", value: Number(d.timeout ?? 0), color: "#56657a" },
        ],
      };
    }).filter((r): r is NonNullable<typeof r> => Boolean(r)),
  );

  const gapRows = payload.generalization_gap.map((g) => ({
    planner: g.planner as string,
    a: Number(g.in_distribution),
    b: Number(g.out_of_distribution),
  }));

  return (
    <div className="space-y-2">
      <div className="grid gap-2 xl:grid-cols-2">
        <Panel title="Mission success · 95% Wilson interval">
          <div className="space-y-3">
            {conditions.map((c) => (
              <div key={c}>
                <p className="mb-0.5 font-mono text-[9px] tracking-[0.16em] text-slate-500">
                  {CONDITION_LABELS[c] ?? c}
                </p>
                <DotCIChart
                  rows={intervalsFor(c).map((r) => ({
                    label: PLANNER_SHORT[r.planner],
                    color: PLANNER_COLOR[r.planner],
                    value: r.success_rate,
                    low: r.success_ci_low,
                    high: r.success_ci_high,
                    note: `${r.successes}/${r.n}`,
                  }))}
                />
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Science fraction · 95% t interval">
          <div className="space-y-3">
            {conditions.map((c) => (
              <div key={c}>
                <p className="mb-0.5 font-mono text-[9px] tracking-[0.16em] text-slate-500">
                  {CONDITION_LABELS[c] ?? c}
                </p>
                <DotCIChart
                  rows={intervalsFor(c).map((r) => ({
                    label: PLANNER_SHORT[r.planner],
                    color: PLANNER_COLOR[r.planner],
                    value: r.science_fraction,
                    low: r.science_ci_low,
                    high: r.science_ci_high,
                  }))}
                />
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="grid gap-2 xl:grid-cols-[1.1fr_1fr]">
        <Panel title="Survival vs science">
          <ParetoPlot points={paretoPoints} />
          <div className="mt-1 flex flex-wrap gap-3 font-mono text-[9px] text-slate-400">
            {PLANNER_ORDER.map((pl) => (
              <span key={pl} className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full" style={{ background: PLANNER_COLOR[pl] }} />
                {PLANNER_SHORT[pl]}
              </span>
            ))}
            <span className="text-slate-500">hover a point for its condition</span>
          </div>
          <p className="mt-1.5 font-mono text-[9px] leading-relaxed text-slate-500">
            No planner dominates. In three of the four Martian conditions the distance-only
            planner survives most often but returns the least science. In the condition
            labelled &ldquo;hardware faults&rdquo; (where faults mostly did not fire) the
            adaptive planner survives most often.
          </p>
        </Panel>
        <Panel title="Paired effect: adaptive − fixed (95% CI, Holm-corrected p)">
          <p className="mb-1 font-mono text-[9px] tracking-[0.16em] text-slate-500">MISSION SUCCESS · McNemar exact</p>
          <ForestPlot rows={forestRows("success")} span={0.4} />
          <p className="mb-1 mt-2 font-mono text-[9px] tracking-[0.16em] text-slate-500">SCIENCE FRACTION · paired t</p>
          <ForestPlot rows={forestRows("science_fraction")} span={0.15} />
        </Panel>
      </div>

      <div className="grid gap-2 xl:grid-cols-[1fr_1.3fr_0.9fr]">
        <Panel
          title="Seed by seed"
          right={
            <select
              value={scatterCondition}
              onChange={(e) => setScatterCondition(e.target.value)}
              className="rounded-sm border border-white/10 bg-black/40 px-1 py-0.5 font-mono text-[9px] text-slate-200"
            >
              {conditions.map((c) => (
                <option key={c} value={c}>
                  {SHORT_COND[c]}
                </option>
              ))}
            </select>
          }
        >
          <PairedScatter points={pairs} />
          <div className="mt-1 grid grid-cols-2 gap-x-2 font-mono text-[8.5px] text-slate-400">
            <span><span className="text-orange-400">●</span> only adaptive returned</span>
            <span><span className="text-sky-300">●</span> only fixed returned</span>
            <span><span className="text-emerald-300">●</span> both returned</span>
            <span><span className="text-slate-500">●</span> neither</span>
          </div>
          {scatterContrast ? (
            <p className="mt-1.5 font-mono text-[9px] text-slate-400">
              Discordant seeds: adaptive {scatterContrast.treatment_only_wins} · fixed{" "}
              {scatterContrast.control_only_wins} of {scatterContrast.n_pairs} matched seeds.
              Seeds with identical values overlap, so fewer dots are visible than seeds; the
              counts are exact.
            </p>
          ) : null}
        </Panel>
        <Panel title="How missions ended">
          <StackedBars rows={stackRows} />
          <div className="mt-2 flex flex-wrap gap-3 font-mono text-[9px] text-slate-400">
            {[
              ["returned safely", "#3ec9a7"],
              ["energy exhausted", "#e8c05a"],
              ["immobilized", "#e8614d"],
              ["timeout", "#56657a"],
            ].map(([k, c]) => (
              <span key={k} className="flex items-center gap-1">
                <span className="h-2 w-3" style={{ background: c }} />
                {k}
              </span>
            ))}
          </div>
        </Panel>
        <Panel title="Moon → Mars: science fraction">
          <SlopeChart rows={gapRows} />
          <p className="mt-1 font-mono text-[9px] leading-relaxed text-slate-500">
            Every planner loses most of its science under the domain shift. The gap G is largest
            for the planner that starts highest, so it is not a ranking of generalization.
          </p>
        </Panel>
      </div>
    </div>
  );
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
            <ChartsSection payload={payload} />

            <details className="group rounded-sm border border-white/10 bg-white/[0.02]">
              <summary className="cursor-pointer select-none px-3 py-2 font-mono text-[10px] tracking-[0.2em] text-slate-300 hover:text-white">
                VIEW RAW RESULTS
                <span className="ml-2 text-slate-500 group-open:hidden">(tables, contrasts, verdict)</span>
              </summary>
              <div className="space-y-2 p-2">
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
                  <li className="text-rose-300">
                    H3 not supported as stated. The &ldquo;hardware faults&rdquo; contrast
                    survived correction, but a post-hoc audit found faults fired in only
                    16&ndash;26% of those missions, and in neither mission on 5 of the 10
                    seeds that drove it. It is not a fault effect.
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
              </div>
            </details>
          </>
        ) : null}
      </div>
    </main>
  );
}

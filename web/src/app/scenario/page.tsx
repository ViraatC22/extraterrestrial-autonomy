"use client";

/**
 * SCENARIO LAB - sensitivity analysis.
 *
 * Sweep one parameter and watch each planner's outcome respond. Every point is
 * a set of complete missions - one mission is one observation, never one
 * timestep - on VALIDATION seeds chosen by the engine, so exploration here
 * cannot touch the held-out terrain behind the confirmatory result. Intervals
 * are computed by the engine (Wilson for success, t for means).
 */

import { useCallback, useState } from "react";

import { PLANNER_COLOR, PLANNER_SHORT, SensitivityChart } from "@/components/Charts";
import { Nav } from "@/components/Nav";
import { Panel } from "@/components/Panels";
import { API_BASE, ApiError } from "@/lib/api";

const SWEEPS: Record<string, { values: number[]; label: string; note: string }> = {
  terrain_uncertainty: {
    values: [0.5, 1.0, 1.5, 2.0, 3.0],
    label: "Terrain uncertainty (× slip dispersion)",
    note: "Multiplies the true spread of wheel slip: the same ground behaves less predictably.",
  },
  risk_budget: {
    values: [0.05, 0.1, 0.2, 0.3, 0.5],
    label: "Risk budget ε",
    note: "Maximum tolerated P(mission failure) for a round trip. Lower is more cautious.",
  },
  comm_delay: {
    values: [0, 10, 20, 40],
    label: "Comm delay (steps per intervention)",
    note: "Steps lost each time the rover stops to ask mission control for help.",
  },
  sensor_noise_scale: {
    values: [0.5, 1, 2, 3],
    label: "Sensor noise (× nominal)",
    note: "Scales remote-sensing error; geometry gets harder to read at range.",
  },
  energy_reserve_fraction: {
    values: [0.1, 0.2, 0.3, 0.4],
    label: "Energy reserve (fraction of battery)",
    note: "Charge the mission insists on keeping in hand for contingency.",
  },
  fault_rate: {
    values: [0, 1, 2, 4],
    label: "Fault rate (scheduled per mission)",
    note:
      "Expected faults scheduled over the step budget. Most missions end early, so many " +
      "scheduled faults never fire (see the research log).",
  },
};

const OUTCOMES: Record<string, { label: string; yMax?: number }> = {
  success: { label: "MISSION SUCCESS", yMax: 1 },
  science_fraction: { label: "SCIENCE FRACTION", yMax: 1 },
  energy_spent: { label: "ENERGY SPENT (Wh)" },
  interventions: { label: "GROUND INTERVENTIONS" },
  severe_slip_events: { label: "SEVERE-SLIP EVENTS" },
};

interface Interval {
  mean: number;
  low: number;
  high: number;
}
interface PointResult {
  value: number;
  planner: string;
  engine: "v1" | "v2";
  n: number;
  seeds: number[];
  success: Interval;
  science_fraction: Interval;
  energy_spent: Interval;
  interventions: Interval;
  severe_slip_events: Interval;
}

export default function ScenarioLab() {
  const [variable, setVariable] = useState("terrain_uncertainty");
  const [planners, setPlanners] = useState<string[]>(["risk_aware_astar", "adaptive_risk_aware_astar"]);
  const [nSeeds, setNSeeds] = useState(6);
  const [body, setBody] = useState("mars");
  const [outcome, setOutcome] = useState("success");
  const [engineMode, setEngineMode] = useState<"v1" | "v2" | "both">("both");
  const [points, setPoints] = useState<PointResult[]>([]);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [swept, setSwept] = useState<{ variable: string; body: string } | null>(null);

  const run = useCallback(async () => {
    setError(null);
    setPoints([]);
    const values = SWEEPS[variable].values;
    const engines: ("v1" | "v2")[] = engineMode === "both" ? ["v1", "v2"] : [engineMode];
    const jobs = values.flatMap((value) =>
      planners.flatMap((planner) => engines.map((engine) => ({ value, planner, engine }))),
    );
    setProgress({ done: 0, total: jobs.length });
    const collected: PointResult[] = [];
    try {
      for (const [i, job] of jobs.entries()) {
        const url =
          `${API_BASE}/sweep-point?variable=${variable}&value=${job.value}` +
          `&planner=${job.planner}&body=${body}&n_seeds=${nSeeds}&engine=${job.engine}`;
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) throw new ApiError((await response.json()).detail ?? response.statusText);
        collected.push((await response.json()) as PointResult);
        setPoints([...collected]);
        setProgress({ done: i + 1, total: jobs.length });
      }
      setSwept({ variable, body });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : `cannot reach the engine at ${API_BASE}`);
    } finally {
      setProgress(null);
    }
  }, [variable, planners, nSeeds, body, engineMode]);

  const shownVariable = swept?.variable ?? variable;
  const series = planners
    .flatMap((planner) =>
      (["v1", "v2"] as const).map((engine) => ({
        planner,
        engine,
        key: `${planner}-${engine}`,
        dashed: engine === "v1",
        points: points
          .filter((p) => p.planner === planner && p.engine === engine)
          .map((p) => ({ x: p.value, ...(p[outcome as keyof PointResult] as Interval) })),
      })),
    )
    .filter((s) => s.points.length);

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-[#07090d]">
      <Nav />
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 p-2 lg:grid-cols-[270px_1fr]">
        <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
          <Panel title="Sweep">
            <div className="space-y-2">
              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">Variable</span>
                <select
                  value={variable}
                  onChange={(e) => setVariable(e.target.value)}
                  className="mt-1 w-full rounded-sm border border-white/10 bg-black/40 px-2 py-1 font-mono text-[11px] text-slate-200"
                >
                  {Object.entries(SWEEPS).map(([key, entry]) => (
                    <option key={key} value={key}>
                      {entry.label}
                    </option>
                  ))}
                </select>
              </label>
              <p className="font-mono text-[9px] leading-relaxed text-slate-500">{SWEEPS[variable].note}</p>
              <p className="font-mono text-[9px] text-slate-400">values: {SWEEPS[variable].values.join(", ")}</p>
              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">Body</span>
                <select
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  className="mt-1 w-full rounded-sm border border-white/10 bg-black/40 px-2 py-1 font-mono text-[11px] text-slate-200"
                >
                  <option value="mars">MARS (lunar prior)</option>
                  <option value="moon">MOON</option>
                </select>
              </label>
              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">Engine</span>
                <select
                  value={engineMode}
                  onChange={(e) => setEngineMode(e.target.value as "v1" | "v2" | "both")}
                  className="mt-1 w-full rounded-sm border border-white/10 bg-black/40 px-2 py-1 font-mono text-[11px] text-slate-200"
                >
                  <option value="both">compare v1 (dashed) and v2 (solid)</option>
                  <option value="v1">v1 · confirmatory engine</option>
                  <option value="v2">v2 · fixed (exploratory)</option>
                </select>
              </label>
              <div>
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">Planners</span>
                {["astar", "risk_aware_astar", "adaptive_risk_aware_astar"].map((name) => (
                  <label key={name} className="mt-1 flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={planners.includes(name)}
                      onChange={(e) =>
                        setPlanners((current) =>
                          e.target.checked ? [...current, name] : current.filter((p) => p !== name),
                        )
                      }
                      className="accent-orange-500"
                    />
                    <span className="h-2 w-2 rounded-full" style={{ background: PLANNER_COLOR[name] }} />
                    <span className="font-mono text-[10px] text-slate-300">{PLANNER_SHORT[name]}</span>
                  </label>
                ))}
              </div>
              <label className="block">
                <span className="flex items-baseline justify-between font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">
                  Missions per point<span className="text-slate-300">{nSeeds}</span>
                </span>
                <input
                  type="range"
                  min={2}
                  max={20}
                  value={nSeeds}
                  onChange={(e) => setNSeeds(Number(e.target.value))}
                  className="mt-1 w-full accent-orange-500"
                />
              </label>
              <button
                onClick={run}
                disabled={Boolean(progress) || planners.length === 0}
                className="w-full rounded-sm border border-orange-500/40 bg-orange-500/10 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.2em] text-orange-300 hover:bg-orange-500/20 disabled:opacity-40"
              >
                {progress ? `point ${progress.done}/${progress.total}` : "run sweep"}
              </button>
              {progress ? (
                <div className="h-[4px] w-full overflow-hidden rounded-sm bg-white/10">
                  <div
                    className="h-full bg-orange-500 transition-[width]"
                    style={{ width: `${(progress.done / progress.total) * 100}%` }}
                  />
                </div>
              ) : null}
              {error ? (
                <p className="rounded-sm border border-rose-500/30 bg-rose-500/10 p-2 font-mono text-[9px] text-rose-300">
                  {error}
                </p>
              ) : null}
            </div>
          </Panel>
          <Panel title="What this is">
            <p className="font-mono text-[9px] leading-relaxed text-slate-400">
              Exploratory only. Missions use the first validation seeds (chosen by the engine), at
              reduced size (44×44 map, 4 targets, 400 steps) so a sweep finishes in about a
              minute. That is not the confirmatory configuration. With a handful of missions per
              point the intervals are wide, and they are shown rather than hidden. The confirmatory
              numbers are on the Experiments page.
            </p>
          </Panel>
        </div>

        <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
          <Panel
            title={series.length ? `${SWEEPS[shownVariable].label} · ${points.length} points` : "Scenario Lab"}
            right={
              <div className="flex gap-1">
                {Object.entries(OUTCOMES).map(([key, spec]) => (
                  <button
                    key={key}
                    onClick={() => setOutcome(key)}
                    className={`rounded-sm border px-2 py-0.5 font-mono text-[8.5px] tracking-[0.14em] ${
                      outcome === key
                        ? "border-orange-500/50 bg-orange-500/15 text-orange-300"
                        : "border-white/10 text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {spec.label}
                  </button>
                ))}
              </div>
            }
          >
            {series.length ? (
              <>
                <SensitivityChart
                  series={series}
                  xLabel={SWEEPS[shownVariable].label}
                  yLabel={OUTCOMES[outcome].label}
                  yMax={OUTCOMES[outcome].yMax}
                />
                <div className="mt-1 flex flex-wrap gap-3 font-mono text-[9px] text-slate-400">
                  {series.map((s) => (
                    <span key={s.key} className="flex items-center gap-1">
                      <svg width="18" height="6">
                        <line
                          x1="0"
                          x2="18"
                          y1="3"
                          y2="3"
                          stroke={PLANNER_COLOR[s.planner]}
                          strokeWidth="2"
                          strokeDasharray={s.dashed ? "4 3" : undefined}
                        />
                      </svg>
                      {PLANNER_SHORT[s.planner]} · {s.engine}
                    </span>
                  ))}
                  <span className="text-slate-500">
                    band = 95% interval ({outcome === "success" ? "Wilson" : "t"}) · each point = {nSeeds}{" "}
                    missions · {swept?.body ?? body}
                  </span>
                </div>
              </>
            ) : (
              <p className="font-mono text-[11px] text-slate-500">
                Pick a variable and run a sweep. Each point is a set of complete missions on matched
                validation terrain; results appear as each point finishes.
              </p>
            )}
          </Panel>
          {points.length ? (
            <Panel title="Points">
              <div className="overflow-x-auto">
                <table className="w-full font-mono text-[10px]">
                  <thead>
                    <tr className="text-slate-500">
                      {["value", "planner", "engine", "n", "success [95%]", "science", "energy Wh", "interventions"].map((h) => (
                        <th key={h} className="px-2 py-1 text-left font-normal">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {points.map((p) => (
                      <tr key={`${p.value}-${p.planner}-${p.engine}`} className="border-t border-white/5">
                        <td className="px-2 py-1 tabular-nums text-slate-300">{p.value}</td>
                        <td className="px-2 py-1 text-slate-200">{PLANNER_SHORT[p.planner]}</td>
                        <td className="px-2 py-1 text-slate-400">{p.engine}</td>
                        <td className="px-2 py-1 tabular-nums text-slate-400">{p.n}</td>
                        <td className="px-2 py-1 tabular-nums text-slate-100">
                          {p.success.mean.toFixed(2)} [{p.success.low.toFixed(2)}, {p.success.high.toFixed(2)}]
                        </td>
                        <td className="px-2 py-1 tabular-nums text-slate-300">{p.science_fraction.mean.toFixed(3)}</td>
                        <td className="px-2 py-1 tabular-nums text-slate-300">{p.energy_spent.mean.toFixed(0)}</td>
                        <td className="px-2 py-1 tabular-nums text-slate-300">{p.interventions.mean.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          ) : null}
        </div>
      </div>
    </main>
  );
}

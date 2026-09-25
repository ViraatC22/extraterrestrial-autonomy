"use client";

/**
 * SCENARIO LAB — change the world and see what breaks.
 *
 * Each point is several complete missions, not several timesteps: one mission
 * is one experimental unit. Sweeps run on VALIDATION seeds, which is what the
 * protocol permits for exploration.
 */

import { useCallback, useMemo, useState } from "react";

import { Nav } from "@/components/Nav";
import { Panel, Readout } from "@/components/Panels";
import { ApiError, DEFAULT_MISSION, getSplits, startMission } from "@/lib/api";
import type { MissionRequest } from "@/lib/types";

const SWEEPS: Record<string, { values: number[]; label: string; note: string }> = {
  terrain_uncertainty: {
    values: [0.5, 1.0, 1.5, 2.0],
    label: "Terrain uncertainty",
    note: "Multiplies the true spread of wheel slip. Higher means the same ground behaves less predictably.",
  },
  fault_rate: {
    values: [0, 0.5, 1, 2],
    label: "Hardware fault rate",
    note: "Expected number of in-mission faults: sensor degradation, motor loss, dust on the panels, wheel damage.",
  },
  comm_delay: {
    values: [0, 10, 20, 40],
    label: "Comm delay",
    note: "Steps lost each time the robot has to stop and ask mission control for help.",
  },
  risk_budget: {
    values: [0.05, 0.1, 0.2, 0.4],
    label: "Risk budget ε",
    note: "Maximum tolerated P(mission failure) for a round trip. Lower is more cautious.",
  },
  sensor_noise_scale: {
    values: [0.5, 1, 2, 3],
    label: "Sensor noise",
    note: "Scales remote-sensing error. Geometry gets harder to read at range.",
  },
};

interface Row {
  value: number;
  planner: string;
  seed: number;
  success: number;
  science: number;
  energy: number;
  interventions: number;
  termination: string;
}

export default function ScenarioLab() {
  const [variable, setVariable] = useState("fault_rate");
  const [planners, setPlanners] = useState<string[]>([
    "risk_aware_astar",
    "adaptive_risk_aware_astar",
  ]);
  const [nSeeds, setNSeeds] = useState(5);
  const [body, setBody] = useState<MissionRequest["body"]>("mars");
  const [rows, setRows] = useState<Row[]>([]);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    setError(null);
    setRows([]);
    try {
      const splits = await getSplits();
      const validation = splits.find((s) => s.name === "validation");
      if (!validation) throw new ApiError("validation split unavailable");

      const seeds = Array.from({ length: nSeeds }, (_, i) => validation.first + i);
      const values = SWEEPS[variable].values;
      const total = values.length * planners.length * seeds.length;
      setProgress({ done: 0, total });

      const collected: Row[] = [];
      let done = 0;
      for (const value of values) {
        for (const planner of planners) {
          for (const seed of seeds) {
            const request: MissionRequest = {
              ...DEFAULT_MISSION,
              body,
              planner,
              seed,
              size: 44,
              n_targets: 4,
              max_steps: 400,
              [variable]: value,
            } as MissionRequest;
            const started = await startMission(request);
            const summary = started.summary;
            collected.push({
              value,
              planner,
              seed,
              success: summary.success ? 1 : 0,
              science: summary.science_fraction,
              energy: summary.energy_spent,
              interventions: summary.interventions,
              termination: summary.termination,
            });
            done += 1;
            setProgress({ done, total });
          }
        }
      }
      setRows(collected);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "engine unreachable");
    } finally {
      setProgress(null);
    }
  }, [variable, planners, nSeeds, body]);

  const summary = useMemo(() => {
    const grouped = new Map<string, Row[]>();
    rows.forEach((row) => {
      const key = `${row.value}|${row.planner}`;
      grouped.set(key, [...(grouped.get(key) ?? []), row]);
    });
    return [...grouped.entries()]
      .map(([key, group]) => {
        const [value, planner] = key.split("|");
        const mean = (pick: (r: Row) => number) =>
          group.reduce((total, row) => total + pick(row), 0) / group.length;
        return {
          value: Number(value),
          planner,
          n: group.length,
          success: mean((r) => r.success),
          science: mean((r) => r.science),
          energy: mean((r) => r.energy),
          interventions: mean((r) => r.interventions),
        };
      })
      .sort((a, b) => a.value - b.value || a.planner.localeCompare(b.planner));
  }, [rows]);

  const maxSuccess = 1;

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-[#07090d]">
      <Nav />
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 p-2 lg:grid-cols-[260px_1fr]">
        <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
          <Panel title="Sweep">
            <div className="space-y-2">
              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">
                  Variable
                </span>
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
              <p className="font-mono text-[9px] leading-relaxed text-slate-500">
                {SWEEPS[variable].note}
              </p>

              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">
                  Body
                </span>
                <select
                  value={body}
                  onChange={(e) => setBody(e.target.value as MissionRequest["body"])}
                  className="mt-1 w-full rounded-sm border border-white/10 bg-black/40 px-2 py-1 font-mono text-[11px] text-slate-200"
                >
                  <option value="mars">MARS</option>
                  <option value="moon">MOON</option>
                </select>
              </label>

              <div>
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">
                  Planners
                </span>
                {["astar", "risk_aware_astar", "adaptive_risk_aware_astar"].map((name) => (
                  <label key={name} className="mt-1 flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={planners.includes(name)}
                      onChange={(e) =>
                        setPlanners((current) =>
                          e.target.checked
                            ? [...current, name]
                            : current.filter((p) => p !== name),
                        )
                      }
                      className="accent-orange-500"
                    />
                    <span className="font-mono text-[10px] text-slate-300">{name}</span>
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
                  max={10}
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
                {progress ? `${progress.done}/${progress.total}` : "run sweep"}
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
              <p className="font-mono text-[9px] leading-relaxed text-slate-600">
                Sweeps use validation seeds. Test and OOD seeds carry the
                confirmatory result and are not used for exploration.
              </p>
            </div>
          </Panel>
        </div>

        <div className="min-h-0 overflow-y-auto">
          {summary.length ? (
            <Panel title={`${SWEEPS[variable].label} — ${rows.length} missions`}>
              <div className="space-y-4">
                {planners.map((planner) => {
                  const series = summary.filter((s) => s.planner === planner);
                  if (!series.length) return null;
                  return (
                    <div key={planner}>
                      <h3 className="mb-2 font-mono text-[10px] tracking-[0.16em] text-slate-300">
                        {planner}
                      </h3>
                      <div className="space-y-1.5">
                        {series.map((point) => (
                          <div key={point.value} className="flex items-center gap-3">
                            <span className="w-14 shrink-0 text-right font-mono text-[10px] tabular-nums text-slate-500">
                              {point.value}
                            </span>
                            <div className="h-[14px] flex-1 overflow-hidden rounded-sm bg-white/[0.05]">
                              <div
                                className="h-full bg-gradient-to-r from-orange-600/70 to-orange-400/70 transition-[width] duration-500"
                                style={{ width: `${(point.success / maxSuccess) * 100}%` }}
                              />
                            </div>
                            <span className="w-32 shrink-0 font-mono text-[10px] tabular-nums text-slate-300">
                              {(point.success * 100).toFixed(0)}% success
                            </span>
                            <span className="w-28 shrink-0 font-mono text-[10px] tabular-nums text-slate-500">
                              sci {point.science.toFixed(3)}
                            </span>
                            <span className="w-24 shrink-0 font-mono text-[10px] tabular-nums text-slate-600">
                              n={point.n}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="mt-3 border-t border-white/10 pt-2 font-mono text-[9px] leading-relaxed text-slate-500">
                Exploratory view on a small number of seeds — no intervals shown.
                The confirmatory numbers with intervals and corrections are on the
                Experiments page.
              </p>
            </Panel>
          ) : (
            <Panel title="Scenario Lab">
              <p className="font-mono text-[11px] text-slate-500">
                Pick a variable and run a sweep. Each point is a set of complete
                missions on matched terrain.
              </p>
              <div className="mt-3 grid grid-cols-2 gap-x-8 md:grid-cols-4">
                <Readout label="Variable" value={SWEEPS[variable].label} />
                <Readout label="Points" value={SWEEPS[variable].values.length} />
                <Readout label="Planners" value={planners.length} />
                <Readout
                  label="Missions"
                  value={SWEEPS[variable].values.length * planners.length * nSeeds}
                />
              </div>
            </Panel>
          )}
        </div>
      </div>
    </main>
  );
}

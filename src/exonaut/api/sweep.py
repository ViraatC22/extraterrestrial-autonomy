"""Sensitivity sweeps for the Scenario Lab.

One sweep point = one parameter value x one planner x n complete missions.
Seeds are always the first n VALIDATION seeds (quarantine excluded), chosen
here rather than by the caller, so exploratory sweeps can never touch the
held-out test or OOD terrain. Each mission is one observation; intervals are
Wilson for success and t for means.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy import stats

from ..simulation import MissionConfig, run_mission

SWEEPABLE = {
    "terrain_uncertainty": (0.1, 4.0),
    "fault_rate": (0.0, 5.0),
    "comm_delay": (0, 100),
    "risk_budget": (0.01, 0.95),
    "sensor_noise_scale": (0.1, 5.0),
    "energy_reserve_fraction": (0.0, 0.9),
    "solar_rate": (0.1, 10.0),
}

#: Reduced mission size so a sweep runs in about a minute. Deliberately not
#: the confirmatory configuration, and labelled as such in the interface.
SWEEP_BASE = {"size": 44, "n_targets": 4, "max_steps": 400}
MAX_SEEDS = 20

_POOL: ProcessPoolExecutor | None = None


def _pool() -> ProcessPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ProcessPoolExecutor()
    return _POOL


def _one(args):
    config, seed = args
    r = run_mission(MissionConfig(**config), seed=seed)
    return {
        "seed": seed,
        "success": bool(r.success),
        "science_fraction": r.science_return / max(r.science_possible, 1e-9),
        "energy_spent": r.energy_spent,
        "interventions": r.interventions,
        "severe_slip_events": r.severe_slip_events,
        "termination": r.termination,
    }


def _t_interval(values: np.ndarray, alpha: float = 0.05) -> tuple[float, float, float]:
    mean = float(values.mean())
    if len(values) < 2:
        return mean, mean, mean
    half = float(
        stats.t.ppf(1 - alpha / 2, len(values) - 1) * values.std(ddof=1) / np.sqrt(len(values))
    )
    return mean, mean - half, mean + half


def run_point(
    variable: str, value: float, planner: str, body: str, n_seeds: int, engine: str = "v1"
) -> dict:
    from ..experiments.protocol import load_splits

    if variable not in SWEEPABLE:
        raise ValueError(f"cannot sweep {variable!r}; choose from {sorted(SWEEPABLE)}")
    lo, hi = SWEEPABLE[variable]
    if not lo <= value <= hi:
        raise ValueError(f"{variable} must lie in [{lo}, {hi}]")
    n_seeds = max(2, min(int(n_seeds), MAX_SEEDS))
    seeds = list(load_splits().get("validation"))[:n_seeds]
    cast = int if variable == "comm_delay" else float
    config = {
        **SWEEP_BASE,
        "body": body,
        "planner": planner,
        "prior_body": "moon",
        "engine": engine,
        variable: cast(value),
    }
    missions = list(_pool().map(_one, [(config, s) for s in seeds]))
    k = sum(m["success"] for m in missions)
    wilson = stats.binomtest(k, len(missions)).proportion_ci(method="wilson")
    out = {
        "variable": variable,
        "value": value,
        "planner": planner,
        "body": body,
        "engine": engine,
        "n": len(missions),
        "seeds": seeds,
        "config": config,
        "success": {
            "mean": k / len(missions),
            "low": float(wilson.low),
            "high": float(wilson.high),
        },
    }
    for key in ("science_fraction", "energy_spent", "interventions", "severe_slip_events"):
        mean, low, high = _t_interval(np.array([m[key] for m in missions], dtype=float))
        out[key] = {"mean": mean, "low": low, "high": high}
    out["missions"] = missions
    return out

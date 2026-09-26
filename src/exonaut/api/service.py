"""Mission session management.

Design decision worth stating, because it is the difference between a
trustworthy interface and a misleading one: a mission is run to completion by
the *same* `run_mission` the experiments call, and the recorded frames are
then streamed. The API does not step the simulator itself.

The alternative - exposing a genuinely incremental stepping interface - would
create a second execution path through the autonomy stack, and any divergence
between it and the research path would mean the interface was showing
something the experiments never measured. Streaming recorded frames is
indistinguishable to a viewer and cannot drift.

Missions are cheap (a few seconds), fully determined by config plus seed, and
cached, so replaying one costs nothing.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import UTC, datetime

import numpy as np

from ..environments import TRUE_CLASS_PARAMS, TerrainClass, make_environment
from ..planners import available_planners, make_planner
from ..simulation import MissionConfig, run_mission
from .models import (
    BeliefSnapshot,
    CandidateEvaluation,
    CandidateRoute,
    Decision,
    MissionRequest,
    MissionSummary,
    PlannerInfo,
    Provenance,
    ScienceTargetOut,
    TelemetryFrame,
    TerrainLayers,
)

CLASS_LABELS = {
    int(TerrainClass.SMOOTH_REGOLITH): "smooth regolith",
    int(TerrainClass.ROCKY): "rocky",
    int(TerrainClass.LOOSE_FINES): "loose fines",
    int(TerrainClass.BEDROCK): "bedrock",
    int(TerrainClass.RIM_TALUS): "rim talus",
}

PLANNER_DESCRIPTIONS = {
    "astar": ("Distance-only A*", "Minimises distance and models no terrain risk at all."),
    "dijkstra": ("Dijkstra", "Uniform-cost search; a control for the A* heuristic."),
    "dstar_lite": ("D* Lite", "Incremental replanner; repairs its search instead of restarting."),
    "risk_aware_astar": (
        "Fixed risk-aware A*",
        "Scores distance, energy, risk and uncertainty, but never revises its terrain model.",
    ),
    "adaptive_risk_aware_astar": (
        "Adaptive risk-aware A*",
        "Identical objective to the fixed planner; the one difference is that measured "
        "slip is folded back into the terrain model, so later routes use corrected beliefs.",
    ),
}


class MissionStore:
    """Bounded in-memory store of completed missions.

    Bounded because each session holds a full frame history; an unbounded dict
    behind a public endpoint is a memory leak with a queue.
    """

    def __init__(self, max_sessions: int = 24):
        self._sessions: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()
        self.max_sessions = max_sessions

    @staticmethod
    def session_key(request: MissionRequest) -> str:
        from ..experiments.provenance import design_digest

        return (
            f"{request.body}-{request.planner}-{request.seed}-{design_digest(request.model_dump())}"
        )

    def run(self, request: MissionRequest) -> tuple[str, dict]:
        key = self.session_key(request)
        with self._lock:
            if key in self._sessions:
                self._sessions.move_to_end(key)
                return key, self._sessions[key]

        config = MissionConfig(**request.to_config_dict())
        result = run_mission(config, seed=request.seed, collect_history=True, collect_belief=True)
        session = {
            "request": request,
            "result": result,
            "executed_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        }

        with self._lock:
            self._sessions[key] = session
            self._sessions.move_to_end(key)
            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)
        return key, session

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                self._sessions.move_to_end(session_id)
            return session

    def drop(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def clear(self) -> int:
        with self._lock:
            count = len(self._sessions)
            self._sessions.clear()
            return count


def terrain_payload(body: str, seed: int, size: int) -> TerrainLayers:
    terrain = make_environment(body, seed=int(seed), size=int(size))
    elevation = terrain.elevation
    return TerrainLayers(
        body=body,
        seed=int(seed),
        size=int(size),
        gravity=float(terrain.gravity),
        elevation=elevation.round(4).tolist(),
        slope=terrain.slope.round(3).tolist(),
        roughness=terrain.roughness.round(4).tolist(),
        illumination=terrain.illumination.round(4).tolist(),
        terrain_class=terrain.terrain_class.astype(int).tolist(),
        hazard=terrain.hazard.tolist(),
        class_labels=CLASS_LABELS,
        elevation_range=(float(elevation.min()), float(elevation.max())),
    )


_GIT_CACHE: dict = {}


def _git() -> dict:
    """Commit the engine is running from, read once per process."""
    if not _GIT_CACHE:
        from ..experiments.provenance import git_provenance

        _GIT_CACHE.update(git_provenance())
    return _GIT_CACHE


def seed_membership(seed: int) -> tuple[str, bool]:
    from ..experiments.protocol import load_quarantine, load_splits

    splits = load_splits()
    quarantine = load_quarantine()
    for name in ("train", "validation", "test", "ood"):
        if seed in splits.get(name, exclude_quarantined=False):
            return name, seed in quarantine.get(name, set())
    return "none", False


def heldout_log_path():
    import os
    from pathlib import Path

    default = Path(__file__).resolve().parents[3] / "data" / "splits" / "heldout_access_log.jsonl"
    return Path(os.environ.get("EXONAUT_HELDOUT_LOG", default))


def record_heldout_access(seed: int, endpoint: str) -> bool:
    """Log any request that exposes an *unused* held-out terrain.

    A future confirmatory study has to run on seeds nobody has looked at. The
    interface can generate any seed, so without a record there would be no
    way to show that. Seeds already evaluated in the confirmatory run, and
    quarantined seeds, are spent and not logged. Returns True if logged.
    """
    import json

    split, quarantined = seed_membership(int(seed))
    if split not in ("test", "ood") or quarantined or int(seed) in confirmatory_seeds():
        return False
    path = heldout_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": int(seed),
        "split": split,
        "endpoint": endpoint,
    }
    with path.open("a") as handle:
        handle.write(json.dumps(entry) + "\n")
    return True


_CONFIRMATORY_SEEDS: set | None = None


def confirmatory_seeds() -> set:
    global _CONFIRMATORY_SEEDS
    if _CONFIRMATORY_SEEDS is None:
        from pathlib import Path

        path = Path(__file__).resolve().parents[3] / "data" / "results" / "exonaut_main.csv"
        try:
            import pandas as pd

            _CONFIRMATORY_SEEDS = set(pd.read_csv(path, usecols=["seed"])["seed"].astype(int))
        except FileNotFoundError:
            _CONFIRMATORY_SEEDS = set()
    return _CONFIRMATORY_SEEDS


def provenance_for(session_id: str, session: dict) -> Provenance:
    from .. import __version__
    from ..experiments.provenance import design_digest

    request: MissionRequest = session["request"]
    config = request.to_config_dict()
    split, quarantined = seed_membership(request.seed)
    git = _git()
    return Provenance(
        run_id=session_id,
        config_digest=design_digest(config),
        config=config,
        git_commit=git.get("commit"),
        git_dirty=git.get("dirty_worktree"),
        engine_version=__version__,
        planner=request.planner,
        planner_adaptive=make_planner(request.planner).adaptive,
        seed=request.seed,
        seed_split=split,
        seed_quarantined=quarantined,
        seed_in_confirmatory_run=request.seed in confirmatory_seeds(),
        executed_utc=session.get("executed_utc", ""),
    )


def decisions_payload(session: dict) -> list[Decision]:
    out = []
    for d in session["result"].decisions:
        out.append(
            Decision(
                index=d["index"],
                step=d["step"],
                row=d["row"],
                col=d["col"],
                charge_fraction=d["charge_fraction"],
                reason=d["reason"],
                risk_budget=d["risk_budget"],
                chosen_route=[tuple(c) for c in d["chosen_route"]],
                candidates=[
                    CandidateRoute(**{**c, "route": [tuple(x) for x in c.get("route", [])]})
                    for c in d["candidates"]
                ],
            )
        )
    return out


def _truth_grids(session: dict) -> tuple[np.ndarray, np.ndarray]:
    """Ground-truth mean slip per cell, from the same terrain method the
    simulator draws slip with (`Terrain.true_slip_mean_grid`)."""
    cached = session.get("_truth")
    if cached is not None:
        return cached
    terrain = session_terrain(session)
    session["_truth"] = (terrain.true_slip_mean_grid(), terrain.terrain_class.astype(int))
    return session["_truth"]


def session_terrain(session: dict):
    """The mission's terrain, rebuilt from its seed (deterministic) and cached."""
    cached = session.get("_terrain")
    if cached is None:
        request: MissionRequest = session["request"]
        cached = make_environment(request.body, seed=request.seed, size=request.size)
        session["_terrain"] = cached
    return cached


def belief_payload(session: dict, index: int) -> BeliefSnapshot | None:
    snap = snapshot_at(session, index)
    if snap is None:
        return None
    truth, true_class = _truth_grids(session)

    def grid(a, digits=4):
        return np.round(np.asarray(a, dtype=float), digits).tolist()

    return BeliefSnapshot(
        frame_index=snap["frame_index"],
        step=snap["step"],
        requested_index=index,
        observed=snap["observed"].astype(int).tolist(),
        believed_class=snap["believed_class"].astype(int).tolist(),
        expected_slip=grid(snap["expected_slip"]),
        slip_sd=grid(snap["slip_sd"]),
        risk=grid(snap["risk"], 6),
        hazard_prob=grid(snap["hazard_prob"]),
        hazard_threshold=snap["hazard_threshold"],
        routable=snap["routable"].astype(int).tolist(),
        true_slip=grid(truth),
        true_class=true_class.tolist(),
    )


def summarize(session_id: str, session: dict) -> MissionSummary:
    result = session["result"]
    request: MissionRequest = session["request"]
    layout = result.mission_layout
    driven = {(f["row"], f["col"]) for f in result.history}
    targets = [
        ScienceTargetOut(
            id=t["id"],
            row=t["row"],
            col=t["col"],
            value=t["value"],
            visited=(t["row"], t["col"]) in driven,
        )
        for t in layout.get("targets", [])
    ]
    true_slip = {int(k): float(v.slip_mean) for k, v in TRUE_CLASS_PARAMS[request.body].items()}
    return MissionSummary(
        run_id=session_id,
        body=request.body,
        planner=request.planner,
        seed=request.seed,
        termination=result.termination,
        success=result.success,
        science_return=result.science_return,
        science_possible=result.science_possible,
        science_fraction=result.science_return / max(result.science_possible, 1e-9),
        targets_visited=result.targets_visited,
        targets_total=result.targets_total,
        energy_spent=result.energy_spent,
        energy_generated=result.energy_generated,
        final_charge=result.final_charge,
        min_charge=result.min_charge,
        steps=result.steps,
        distance_travelled=result.distance_travelled,
        interventions=result.interventions,
        severe_slip_events=result.severe_slip_events,
        mean_slip=result.mean_slip,
        planner_replans=result.planner_replans,
        nodes_expanded=result.nodes_expanded,
        hazard_refusals=result.hazard_refusals,
        final_distance_from_home=result.final_distance_from_home,
        home=tuple(layout.get("home", (0, 0))),
        targets=targets,
        true_class_slip=true_slip,
        n_frames=len(result.history),
        n_decisions=len(result.decisions),
        provenance=provenance_for(session_id, session),
    )


def frame_payload(frame: dict) -> TelemetryFrame:
    return TelemetryFrame(
        step=frame["step"],
        row=frame["row"],
        col=frame["col"],
        charge=frame["charge"],
        charge_fraction=frame["charge_fraction"],
        science=frame["science"],
        targets_visited=frame["targets_visited"],
        slip=frame["slip"],
        moved=frame["moved"],
        reason=frame["reason"],
        returning=frame["returning"],
        goal=tuple(frame["goal"]) if frame.get("goal") else None,
        planned_path=[tuple(cell) for cell in frame.get("planned_path", [])],
        interventions=frame["interventions"],
        predicted_failure_prob=frame["predicted_failure_prob"],
        belief={int(k): float(v) for k, v in frame["belief"].items()},
        belief_sd={int(k): float(v) for k, v in frame["belief_sd"].items()},
        decision_reason=frame.get("decision_reason"),
        candidates=[CandidateEvaluation(**c) for c in frame.get("candidates", [])],
        decision_index=frame.get("decision_index", -1),
        sensing_radius=frame.get("sensing_radius"),
        heading_deg=frame.get("heading_deg"),
        local_slope_deg=frame.get("local_slope_deg"),
    )


def planner_catalogue() -> list[PlannerInfo]:
    entries = []
    for name in available_planners():
        label, description = PLANNER_DESCRIPTIONS.get(name, (name, ""))
        entries.append(
            PlannerInfo(
                name=name,
                label=label,
                adaptive=make_planner(name).adaptive,
                description=description,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# Terrain probe
# ---------------------------------------------------------------------------


def _row(key, label, value, display, unit, status, group):
    return {
        "key": key,
        "label": label,
        "value": value,
        "display": display,
        "unit": unit,
        "status": status,
        "group": group,
    }


def _probability(p: float) -> str:
    return "< 1e-5" if p < 1e-5 else f"{p:.1e}" if p < 1e-3 else f"{p:.4f}"


def probe_payload(terrain, row: int, col: int, solar_rate: float, snapshot: dict | None) -> dict:
    """Every value the interface shows for one cell, computed here.

    The interface only lays these rows out. Anything derived - solar harvest,
    whether the planner would route through the cell, the chance a single
    entry ends the mission - is computed by the engine's own functions, so a
    probe cannot disagree with what the simulator or planner used.
    """
    from ..robot.power import PowerSystem

    if not (0 <= row < terrain.size and 0 <= col < terrain.size):
        raise ValueError(f"cell ({row}, {col}) is outside the {terrain.size}x{terrain.size} map")
    elevation = terrain.elevation
    illum = float(terrain.illumination[row, col])
    # the power model's own recharge rule on a battery with room to spare
    harvest = PowerSystem(capacity=1e9, charge=0.0, solar_rate=solar_rate).recharge(illum)
    true_mean, _ = terrain.true_slip_distribution(row, col)
    klass = int(terrain.terrain_class[row, col])
    rows = [
        _row(
            "elevation",
            "ELEVATION",
            float(elevation[row, col] - elevation.min()),
            f"{elevation[row, col] - elevation.min():.2f}",
            "m above map min",
            "GENERATED",
            "truth",
        ),
        _row(
            "slope",
            "SLOPE",
            float(terrain.slope[row, col]),
            f"{terrain.slope[row, col]:.1f}",
            "°",
            "GENERATED",
            "truth",
        ),
        _row(
            "roughness",
            "ROUGHNESS",
            float(terrain.roughness[row, col]),
            f"{terrain.roughness[row, col]:.2f}",
            "index",
            "GENERATED",
            "truth",
        ),
        _row("class", "CLASS", klass, CLASS_LABELS[klass], "", "GENERATED", "truth"),
        _row(
            "hazard",
            "HAZARD",
            bool(terrain.hazard[row, col]),
            "IMPASSABLE" if terrain.hazard[row, col] else "passable",
            "",
            "GENERATED",
            "truth",
        ),
        _row(
            "illumination",
            "ILLUMINATION",
            illum,
            f"{illum:.2f}",
            "× nominal",
            "GENERATED",
            "truth",
        ),
        _row(
            "solar_harvest",
            "SOLAR HARVEST",
            float(harvest),
            f"{harvest:.2f}",
            "Wh/step, clean panels",
            "ASSUMED",
            "truth",
        ),
        _row(
            "true_slip",
            "TRUE MEAN SLIP",
            float(true_mean),
            f"{true_mean:.3f}",
            "",
            "SIMULATED",
            "truth",
        ),
    ]
    out = {
        "row": row,
        "col": col,
        "belief_step": None,
        "belief_frame_index": None,
        "observed": None,
        "rows": rows,
    }
    if snapshot is None:
        return out

    seen = bool(snapshot["observed"][row, col])
    mean = float(snapshot["expected_slip"][row, col])
    sd = float(snapshot["slip_sd"][row, col])
    hazard_p = float(snapshot["hazard_prob"][row, col])
    cell_risk = float(snapshot["risk"][row, col])
    believed_class = int(snapshot["believed_class"][row, col])
    rows += [
        _row(
            "believed_class",
            "BELIEVED CLASS",
            believed_class if seen else None,
            CLASS_LABELS.get(believed_class, "?") if seen else "unknown",
            "",
            "INFERRED",
            "belief",
        ),
        _row(
            "believed_slope",
            "BELIEVED SLOPE",
            float(snapshot["believed_slope"][row, col]) if seen else None,
            f"{snapshot['believed_slope'][row, col]:.1f}" if seen else "not sensed",
            "°" if seen else "",
            "INFERRED",
            "belief",
        ),
        _row(
            "believed_slip",
            "BELIEVED SLIP",
            mean,
            f"{mean:.3f} ± {sd:.3f}",
            "mean ± s.d.",
            "INFERRED",
            "belief",
        ),
        _row("hazard_prob", "P(HAZARD)", hazard_p, f"{hazard_p:.2f}", "", "INFERRED", "belief"),
        _row(
            "routable",
            "ROUTABLE",
            bool(snapshot["routable"][row, col]),
            "yes" if snapshot["routable"][row, col] else "no",
            "",
            "INFERRED",
            "belief",
        ),
        _row(
            "cell_risk",
            "P(ENTRY ENDS MISSION)",
            cell_risk,
            _probability(cell_risk),
            "",
            "INFERRED",
            "belief",
        ),
    ]
    out.update(
        belief_step=int(snapshot["step"]),
        belief_frame_index=int(snapshot["frame_index"]),
        observed=seen,
        rows=rows,
    )
    return out


def snapshot_at(session: dict, index: int) -> dict | None:
    """The belief snapshot in force at a frame (the latest one at or before it)."""
    snapshots = session["result"].belief_frames
    eligible = [s for s in snapshots if s["frame_index"] <= index]
    if eligible:
        return eligible[-1]
    return snapshots[0] if snapshots else None

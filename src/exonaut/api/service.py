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

from ..environments import TRUE_CLASS_PARAMS, TerrainClass, make_environment
from ..planners import available_planners, make_planner
from ..simulation import MissionConfig, run_mission
from .models import (
    CandidateEvaluation,
    MissionRequest,
    MissionSummary,
    PlannerInfo,
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
        result = run_mission(config, seed=request.seed, collect_history=True)
        session = {"request": request, "result": result}

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

"""Wire types for the mission-control API.

These are the contract between the Python research engine and the TypeScript
frontend. They are deliberately thin: the frontend renders state, it never
computes science. Any number that appears in the interface has to have been
produced by `exonaut` and passed through here, so the interface cannot drift
from the experiments.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MissionRequest(BaseModel):
    body: str = Field("mars", description="planetary body: 'moon' or 'mars'")
    planner: str = Field("adaptive_risk_aware_astar")
    seed: int = Field(200000)
    size: int = Field(56, ge=16, le=128)
    n_targets: int = Field(4, ge=1, le=12)
    max_steps: int = Field(600, ge=50, le=2000)
    risk_budget: float = Field(0.20, ge=0.01, le=0.95)
    fault_rate: float = Field(0.0, ge=0.0, le=5.0)
    comm_delay: int = Field(0, ge=0, le=100)
    terrain_uncertainty: float = Field(1.0, ge=0.1, le=4.0)
    sensor_noise_scale: float = Field(1.0, ge=0.1, le=5.0)
    sensing_radius: int = Field(6, ge=2, le=20)
    solar_rate: float = Field(2.0, ge=0.1, le=10.0)
    energy_reserve_fraction: float = Field(0.25, ge=0.0, le=0.9)
    prior_body: str = Field("moon", description="body the world-model prior came from")
    engine: str = Field(
        "v1",
        pattern="^v[12]$",
        description="v1 = the engine the confirmatory study ran on; v2 = with the fixes "
        "in docs/RESEARCH_LOG.md (exploratory)",
    )

    def to_config_dict(self) -> dict:
        data = self.model_dump()
        data.pop("seed")
        return data


class TerrainLayers(BaseModel):
    """Ground-truth rasters for rendering.

    The frontend receives terrain truth because it is drawing the world, not
    driving in it. What the *robot* knew at each step is carried separately on
    the telemetry frames.
    """

    body: str
    seed: int
    size: int
    gravity: float
    elevation: list[list[float]]
    slope: list[list[float]]
    roughness: list[list[float]]
    illumination: list[list[float]]
    terrain_class: list[list[int]]
    hazard: list[list[bool]]
    class_labels: dict[int, str]
    elevation_range: tuple[float, float]


class ScienceTargetOut(BaseModel):
    id: int
    row: int
    col: int
    value: float
    visited: bool


class CandidateEvaluation(BaseModel):
    """One science target as the planner scored it at a decision point.

    Rejected candidates are included with their reason: a planner that only
    reports its winner cannot be audited.
    """

    target_id: int
    row: int
    col: int
    science_value: float
    reachable: bool
    selected: bool = False
    rejected: str | None = None
    path_cells: int | None = None
    expected_energy: float | None = None
    energy_sd: float | None = None
    expected_solar_income: float | None = None
    p_failure: float | None = None
    p_terrain: float | None = None
    p_energy: float | None = None
    utility: float | None = None
    #: reachable and P(failure) <= risk budget, as the mission manager decided it
    within_budget: bool = False
    #: 1 = highest utility among within-budget candidates (the one selected)
    feasible_rank: int | None = None


class TelemetryFrame(BaseModel):
    """One mission step, as the mission-control view consumes it."""

    step: int
    row: int
    col: int
    charge: float
    charge_fraction: float
    science: float
    targets_visited: int
    slip: float
    moved: bool
    reason: str
    returning: bool
    goal: tuple[int, int] | None
    planned_path: list[tuple[int, int]]
    interventions: int
    predicted_failure_prob: float
    belief: dict[int, float]
    belief_sd: dict[int, float]
    decision_reason: str | None = None
    candidates: list[CandidateEvaluation] = []
    #: index into /missions/{id}/decisions for the decision in force this frame
    decision_index: int = -1
    #: sensing radius actually in effect (sensor faults shrink it)
    sensing_radius: int | None = None
    #: grid heading of the last completed move, degrees clockwise from grid
    #: north (row 0); None before the rover first moves
    heading_deg: float | None = None
    #: generated slope of the cell the rover occupies
    local_slope_deg: float | None = None


class MissionSummary(BaseModel):
    run_id: str
    body: str
    planner: str
    seed: int
    termination: str
    success: bool
    science_return: float
    science_possible: float
    science_fraction: float
    targets_visited: int
    targets_total: int
    energy_spent: float
    energy_generated: float
    final_charge: float
    min_charge: float
    steps: int
    distance_travelled: float
    interventions: int
    severe_slip_events: int
    mean_slip: float
    planner_replans: int
    nodes_expanded: int
    hazard_refusals: int
    final_distance_from_home: float
    home: tuple[int, int]
    targets: list[ScienceTargetOut]
    true_class_slip: dict[int, float]
    n_frames: int
    n_decisions: int = 0
    provenance: Provenance | None = None


class Provenance(BaseModel):
    """Where a displayed mission came from, precisely enough to reproduce it.

    `seed_split` matters for honesty: a seed from the held-out test or OOD
    splits is flagged, because viewing one in the interface means its terrain
    has been seen, even though viewing cannot change any committed result.
    """

    run_id: str
    config_digest: str
    config: dict
    git_commit: str | None
    git_dirty: bool | None
    engine_version: str
    planner: str
    planner_adaptive: bool
    seed: int
    seed_split: str
    seed_quarantined: bool
    #: True when this seed was already evaluated in the committed confirmatory
    #: run, so replaying it reproduces a published row rather than exposing
    #: an unused held-out terrain
    seed_in_confirmatory_run: bool = False
    executed_utc: str


class CandidateRoute(CandidateEvaluation):
    route: list[tuple[int, int]] = []


class Decision(BaseModel):
    """One planning decision, with the route evaluated for every candidate."""

    index: int
    step: int
    row: int
    col: int
    charge_fraction: float
    reason: str | None
    risk_budget: float
    chosen_route: list[tuple[int, int]]
    candidates: list[CandidateRoute]


class BeliefSnapshot(BaseModel):
    """Whole-map belief at (or just before) a frame, next to ground truth.

    Everything under "belief" is what the planner itself consults; the
    `true_slip` grid is simulator ground truth, which the rover never sees.
    Snapshots are recorded every few frames, so `frame_index` may be earlier
    than the frame requested - the UI shows which one it is.
    """

    frame_index: int
    step: int
    requested_index: int
    observed: list[list[int]]
    believed_class: list[list[int]]
    expected_slip: list[list[float]]
    slip_sd: list[list[float]]
    risk: list[list[float]]
    hazard_prob: list[list[float]]
    hazard_threshold: float
    #: the planner's own traversability test per cell (1 = it would route here)
    routable: list[list[int]] = []
    true_slip: list[list[float]]
    true_class: list[list[int]]


class MissionStarted(BaseModel):
    session_id: str
    summary: MissionSummary


class PlannerInfo(BaseModel):
    name: str
    label: str
    adaptive: bool
    description: str


class SplitInfo(BaseModel):
    name: str
    size: int
    first: int
    last: int
    quarantined: list[int]

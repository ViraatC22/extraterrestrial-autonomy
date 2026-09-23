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

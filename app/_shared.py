"""Shared helpers for the EXONAUT dashboard.

The dashboard is a presentation layer over the experiment engine; it must not
become a second implementation of the science. Everything here either renders
state produced by `exonaut`, or calls into it. No statistics are computed in
this module.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from exonaut.environments import TerrainClass, make_environment  # noqa: E402
from exonaut.simulation import MissionConfig, run_mission  # noqa: E402

RESULTS_DIR = PROJECT_ROOT / "data" / "results"
DOCS_DIR = PROJECT_ROOT / "docs"

PLANNER_LABELS = {
    "astar": "Distance-only A*",
    "dijkstra": "Dijkstra (no heuristic)",
    "dstar_lite": "D* Lite (incremental)",
    "risk_aware_astar": "Fixed risk-aware A*",
    "adaptive_risk_aware_astar": "Adaptive risk-aware A* (ours)",
}
CONDITION_LABELS = {
    "moon_id": "Moon (in-distribution)",
    "mars_ood": "Mars (out-of-distribution)",
    "mars_high_uncertainty": "Mars, 1.5x slip dispersion",
    "mars_faults": "Mars, hardware faults",
    "mars_comm_delay": "Mars, 20-step comm delay",
}
CLASS_LABELS = {
    int(TerrainClass.SMOOTH_REGOLITH): "smooth regolith",
    int(TerrainClass.ROCKY): "rocky",
    int(TerrainClass.LOOSE_FINES): "loose fines",
    int(TerrainClass.BEDROCK): "bedrock",
    int(TerrainClass.RIM_TALUS): "rim talus",
}

TERMINATION_COLORS = {
    "success": "#2a9d8f",
    "energy_exhausted": "#e9c46a",
    "immobilized": "#e76f51",
    "timeout": "#8d99ae",
}


def page_setup(title: str, icon: str = "🛰️") -> None:
    st.set_page_config(page_title=f"EXONAUT — {title}", page_icon=icon, layout="wide")


@st.cache_data(show_spinner=False)
def get_terrain(body: str, seed: int, size: int):
    """Terrain is deterministic in (body, seed, size), so it is safe to cache
    and never needs to be stored in a result file."""
    return make_environment(body, seed=int(seed), size=int(size))


@st.cache_data(show_spinner="Running mission…")
def cached_mission(config_dict: dict, seed: int):
    """Run one mission with replay recording.

    Cached on the exact config so re-rendering the page does not silently
    re-run the simulation, which would make the displayed trajectory drift
    from the numbers beside it.
    """
    result = run_mission(MissionConfig(**config_dict), seed=int(seed), collect_history=True)
    return result


@st.cache_data(show_spinner=False)
def load_results(name: str = "exonaut_main"):
    from exonaut.experiments.io import load_results as _load

    return _load(name, results_dir=RESULTS_DIR)


def available_result_sets() -> list[str]:
    stems = set()
    for pattern in ("*.parquet", "*.csv"):
        for path in RESULTS_DIR.glob(pattern):
            if path.stem.endswith(("_primary", "_secondary")):
                continue
            stems.add(path.stem)
    return sorted(stems)


# ---------------------------------------------------------------------------
# Terrain rendering
# ---------------------------------------------------------------------------
LAYERS = {
    "Terrain class": ("terrain_class", "Portland"),
    "Elevation (m)": ("elevation", "Greys"),
    "Slope (deg)": ("slope", "Inferno"),
    "Roughness": ("roughness", "Cividis"),
    "Illumination": ("illumination", "Solar"),
}


def terrain_figure(
    terrain,
    layer: str = "Terrain class",
    path=None,
    planned=None,
    rover=None,
    home=None,
    targets=None,
    title: str | None = None,
    height: int = 620,
):
    """Interactive terrain map with the rover's route drawn over it."""
    field_name, colorscale = LAYERS.get(layer, LAYERS["Terrain class"])
    field = getattr(terrain, field_name).astype(float)

    if field_name == "terrain_class":
        hover = np.vectorize(lambda v: CLASS_LABELS.get(int(v), str(int(v))))(field)
        heat = go.Heatmap(
            z=field,
            colorscale=colorscale,
            showscale=False,
            customdata=hover,
            hovertemplate="%{customdata}<extra></extra>",
        )
    else:
        heat = go.Heatmap(
            z=field,
            colorscale=colorscale,
            colorbar=dict(title=layer, thickness=12),
            hovertemplate=f"{layer}: %{{z:.2f}}<extra></extra>",
        )

    fig = go.Figure(heat)

    # Hazards as a translucent red overlay: they are the terrain the robot
    # refuses outright, so they read better as a mask than as another layer.
    hazard = np.where(terrain.hazard, 1.0, np.nan)
    fig.add_trace(
        go.Heatmap(
            z=hazard,
            colorscale=[[0, "rgba(231,111,81,0.55)"], [1, "rgba(231,111,81,0.55)"]],
            showscale=False,
            hoverinfo="skip",
        )
    )

    if planned:
        fig.add_trace(
            go.Scatter(
                x=[c for _, c in planned],
                y=[r for r, _ in planned],
                mode="lines",
                line=dict(color="#bfc9ff", width=2, dash="dot"),
                name="planned route",
                hoverinfo="skip",
            )
        )
    if path:
        fig.add_trace(
            go.Scatter(
                x=[c for _, c in path],
                y=[r for r, _ in path],
                mode="lines",
                line=dict(color="#4cc9f0", width=3),
                name="driven path",
                hoverinfo="skip",
            )
        )
    if targets:
        pending = [t for t in targets if not t.get("visited")]
        done = [t for t in targets if t.get("visited")]
        if pending:
            fig.add_trace(
                go.Scatter(
                    x=[t["col"] for t in pending],
                    y=[t["row"] for t in pending],
                    mode="markers",
                    name="science target",
                    marker=dict(
                        symbol="diamond",
                        size=13,
                        color="#ffd166",
                        line=dict(color="#1d1d1d", width=1),
                    ),
                    text=[f"target {t['id']} (value {t['value']:.2f})" for t in pending],
                    hovertemplate="%{text}<extra></extra>",
                )
            )
        if done:
            fig.add_trace(
                go.Scatter(
                    x=[t["col"] for t in done],
                    y=[t["row"] for t in done],
                    mode="markers",
                    name="collected",
                    marker=dict(
                        symbol="diamond",
                        size=13,
                        color="#2a9d8f",
                        line=dict(color="#1d1d1d", width=1),
                    ),
                    hoverinfo="skip",
                )
            )
    if home:
        fig.add_trace(
            go.Scatter(
                x=[home[1]],
                y=[home[0]],
                mode="markers",
                name="lander",
                marker=dict(
                    symbol="square", size=15, color="#f1faee", line=dict(color="#1d1d1d", width=1)
                ),
                hovertemplate="lander<extra></extra>",
            )
        )
    if rover:
        fig.add_trace(
            go.Scatter(
                x=[rover[1]],
                y=[rover[0]],
                mode="markers",
                name="rover",
                marker=dict(
                    symbol="circle", size=16, color="#ef476f", line=dict(color="white", width=2)
                ),
                hovertemplate="rover<extra></extra>",
            )
        )

    fig.update_layout(
        title=title,
        height=height,
        margin=dict(l=10, r=10, t=40 if title else 10, b=10),
        yaxis=dict(autorange="reversed", scaleanchor="x", constrain="domain"),
        xaxis=dict(constrain="domain"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def belief_figure(frames, true_values: dict | None = None, height: int = 320):
    """How the robot's per-class slip belief moved during the mission.

    This is the clearest single view of adaptation: the lines move only if the
    world model is being revised, so a fixed planner shows flat lines by
    construction.
    """
    fig = go.Figure()
    steps = [f["step"] for f in frames]
    for klass, label in CLASS_LABELS.items():
        values = [f["belief"].get(klass) for f in frames]
        if not any(v is not None for v in values):
            continue
        fig.add_trace(go.Scatter(x=steps, y=values, mode="lines", name=label))
        if true_values and klass in true_values:
            fig.add_hline(
                y=true_values[klass],
                line_dash="dot",
                line_width=1,
                opacity=0.45,
                annotation_text=f"true {label}",
                annotation_position="right",
                annotation_font_size=9,
            )
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_title="mission step",
        yaxis_title="believed mean slip",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def metric_row(result) -> None:
    columns = st.columns(5)
    fraction = result.science_return / max(result.science_possible, 1e-9)
    columns[0].metric("Outcome", "SUCCESS" if result.success else result.termination.upper())
    columns[1].metric(
        "Science returned",
        f"{fraction:.0%}",
        f"{result.targets_visited}/{result.targets_total} targets",
    )
    columns[2].metric("Energy spent", f"{result.energy_spent:.0f} Wh")
    columns[3].metric("Steps", result.steps)
    columns[4].metric("Ground interventions", result.interventions)

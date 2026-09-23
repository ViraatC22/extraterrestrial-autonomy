"""Every planner on the same terrain, routes drawn side by side."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from _shared import (  # noqa: E402
    LAYERS,
    PLANNER_LABELS,
    cached_mission,
    get_terrain,
    page_setup,
    terrain_figure,
)
from exonaut.experiments.protocol import load_splits  # noqa: E402

page_setup("Algorithm Comparison")
st.title("Algorithm Comparison")
st.caption(
    "Identical terrain, identical targets, identical faults — only the planner "
    "changes. This is the paired design the statistics rest on, shown for one seed."
)

splits = load_splits()

with st.sidebar:
    st.header("Comparison")
    body = st.selectbox("Body", ["mars", "moon"], index=0)
    split_name = st.selectbox("Seed split", ["validation", "test", "ood"], index=0)
    seeds = splits.get(split_name)
    seed = st.select_slider("Terrain seed", options=list(seeds[:40]), value=seeds[0])
    chosen = st.multiselect(
        "Planners",
        list(PLANNER_LABELS),
        default=["astar", "risk_aware_astar", "adaptive_risk_aware_astar"],
        format_func=lambda k: PLANNER_LABELS[k],
    )
    size = st.slider("Map size", 32, 72, 56, step=8)
    max_steps = st.slider("Step budget", 200, 1000, 600, step=100)
    fault_rate = st.slider("Expected faults", 0.0, 3.0, 0.0, step=0.5)
    layer = st.selectbox("Map layer", list(LAYERS), index=0)

if not chosen:
    st.info("Select at least one planner.")
    st.stop()

terrain = get_terrain(body, seed, size)
results = {}
for planner in chosen:
    results[planner] = cached_mission(
        dict(
            body=body,
            planner=planner,
            size=size,
            n_targets=4,
            max_steps=max_steps,
            fault_rate=fault_rate,
            solar_rate=2.0,
            energy_reserve_fraction=0.25,
            prior_body="moon",
        ),
        int(seed),
    )

summary = pd.DataFrame(
    [
        {
            "Planner": PLANNER_LABELS[planner],
            "Outcome": "success" if r.success else r.termination,
            "Science": r.science_return / max(r.science_possible, 1e-9),
            "Targets": f"{r.targets_visited}/{r.targets_total}",
            "Energy (Wh)": round(r.energy_spent, 1),
            "Steps": r.steps,
            "Interventions": r.interventions,
            "Severe slips": r.severe_slip_events,
            "Replans": r.planner_replans,
            "Nodes expanded": r.nodes_expanded,
        }
        for planner, r in results.items()
    ]
)
st.dataframe(summary, use_container_width=True, hide_index=True)

columns = st.columns(min(len(chosen), 3))
for index, (planner, result) in enumerate(results.items()):
    with columns[index % len(columns)]:
        driven = [(f["row"], f["col"]) for f in result.history] or [
            tuple(result.mission_layout.get("home", (0, 0)))
        ]
        st.plotly_chart(
            terrain_figure(
                terrain,
                layer=layer,
                path=driven,
                rover=driven[-1],
                home=result.mission_layout.get("home"),
                targets=result.mission_layout.get("targets"),
                title=f"{PLANNER_LABELS[planner]} — "
                f"{'success' if result.success else result.termination}",
                height=460,
            ),
            use_container_width=True,
        )

st.info(
    "Reading the routes: the distance-only planner takes short, blunt lines "
    "through whatever is in the way. Risk-aware planners detour around suspect "
    "ground — which is safer per metre but costs metres, and on terrain where "
    "nearly everything is suspect that trade can go the wrong way. That effect "
    "is visible in the confirmatory results on the Results page."
)

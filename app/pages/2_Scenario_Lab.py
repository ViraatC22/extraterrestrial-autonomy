"""Change the world and see what breaks."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from _shared import PLANNER_LABELS, cached_mission, page_setup  # noqa: E402
from exonaut.experiments.protocol import load_splits  # noqa: E402

page_setup("Scenario Lab")
st.title("Scenario Lab")
st.caption(
    "Sweep one environmental variable and watch the outcome move. Each point is "
    "several complete missions, not several timesteps — one mission is one "
    "experimental unit."
)

splits = load_splits()
validation = splits.get("validation")

with st.sidebar:
    st.header("Sweep")
    body = st.selectbox("Body", ["mars", "moon"], index=0)
    planners = st.multiselect(
        "Planners",
        list(PLANNER_LABELS),
        default=["risk_aware_astar", "adaptive_risk_aware_astar"],
        format_func=lambda k: PLANNER_LABELS[k],
    )
    variable = st.selectbox(
        "Variable to sweep",
        [
            "terrain_uncertainty",
            "fault_rate",
            "comm_delay",
            "risk_budget",
            "solar_rate",
            "energy_reserve_fraction",
            "n_targets",
        ],
    )
    n_seeds = st.slider(
        "Missions per point", 3, 20, 6, help="More seeds means a steadier curve and a longer wait."
    )
    size = st.slider("Map size", 32, 72, 48, step=8)
    max_steps = st.slider("Step budget", 200, 900, 500, step=100)

SWEEPS = {
    "terrain_uncertainty": [0.5, 1.0, 1.5, 2.0],
    "fault_rate": [0.0, 0.5, 1.0, 2.0],
    "comm_delay": [0, 10, 20, 40],
    "risk_budget": [0.05, 0.1, 0.2, 0.4],
    "solar_rate": [1.0, 2.0, 3.0],
    "energy_reserve_fraction": [0.1, 0.25, 0.4],
    "n_targets": [2, 4, 6],
}
values = SWEEPS[variable]

st.write(
    f"**{variable}** over `{values}` — {len(values) * len(planners) * n_seeds} missions total."
)

if not planners:
    st.info("Select at least one planner.")
    st.stop()

if st.button("Run sweep", type="primary"):
    rows = []
    total = len(values) * len(planners) * n_seeds
    done = 0
    progress = st.progress(0.0, text="running…")
    for value in values:
        for planner in planners:
            for seed in validation[:n_seeds]:
                config = dict(
                    body=body,
                    planner=planner,
                    size=size,
                    n_targets=4,
                    max_steps=max_steps,
                    solar_rate=2.0,
                    energy_reserve_fraction=0.25,
                    prior_body="moon",
                )
                config[variable] = value
                result = cached_mission(config, int(seed))
                rows.append(
                    {
                        variable: value,
                        "planner": PLANNER_LABELS[planner],
                        "seed": int(seed),
                        "success": float(result.success),
                        "science_fraction": result.science_return
                        / max(result.science_possible, 1e-9),
                        "energy_spent": result.energy_spent,
                        "interventions": result.interventions,
                        "termination": result.termination,
                    }
                )
                done += 1
                progress.progress(done / total, text=f"{done}/{total} missions")
    progress.empty()
    st.session_state["scenario_rows"] = rows

rows = st.session_state.get("scenario_rows")
if not rows:
    st.info("Configure a sweep and press **Run sweep**.")
    st.stop()

frame = pd.DataFrame(rows)
if variable not in frame.columns:
    st.warning("The stored sweep used a different variable. Re-run.")
    st.stop()

summary = (
    frame.groupby([variable, "planner"])
    .agg(
        success_rate=("success", "mean"),
        science=("science_fraction", "mean"),
        energy=("energy_spent", "mean"),
        interventions=("interventions", "mean"),
        n=("success", "size"),
    )
    .reset_index()
)

metric = st.radio(
    "Outcome",
    ["success_rate", "science", "energy", "interventions"],
    horizontal=True,
)
figure = px.line(
    summary,
    x=variable,
    y=metric,
    color="planner",
    markers=True,
    labels={metric: metric.replace("_", " ")},
)
figure.update_layout(
    height=430,
    paper_bgcolor="rgba(0,0,0,0)",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(figure, use_container_width=True)

st.caption(
    f"Each point averages {summary['n'].iloc[0]} missions. Error is not shown "
    "because this is an exploratory view on validation seeds — the confirmatory "
    "numbers with intervals are on the Results page."
)

st.subheader("How missions ended")
termination = frame.groupby(["planner", "termination"]).size().reset_index(name="count")
st.plotly_chart(
    px.bar(
        termination,
        x="planner",
        y="count",
        color="termination",
        barmode="stack",
        color_discrete_map={
            "success": "#2a9d8f",
            "energy_exhausted": "#e9c46a",
            "immobilized": "#e76f51",
            "timeout": "#8d99ae",
        },
    ),
    use_container_width=True,
)

with st.expander("Raw rows"):
    st.dataframe(frame, use_container_width=True)

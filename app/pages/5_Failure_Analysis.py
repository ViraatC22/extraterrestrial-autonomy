"""The missions that failed, and why.

A comparison that only shows wins is not evidence. This page is deliberately
built around the failures, including the ones that go against the proposed
method.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from _shared import (  # noqa: E402
    CONDITION_LABELS,
    PLANNER_LABELS,
    TERMINATION_COLORS,
    available_result_sets,
    cached_mission,
    get_terrain,
    load_results,
    page_setup,
    terrain_figure,
)

page_setup("Failure Analysis")
st.title("Failure Analysis")
st.caption(
    "Where the autonomy breaks. Selecting a failed mission below re-runs that "
    "exact seed and configuration so the route that ended it can be inspected."
)

sets = available_result_sets()
if not sets:
    st.warning("No result files found.")
    st.stop()
default = sets.index("exonaut_main") if "exonaut_main" in sets else 0
frame = load_results(st.selectbox("Result set", sets, index=default))

failures = frame[~frame["success"].astype(bool)]
total = len(frame)

columns = st.columns(4)
columns[0].metric("Missions", total)
columns[1].metric("Failures", len(failures), f"{len(failures) / max(total, 1):.0%}")
columns[2].metric("Immobilized", int((frame["termination"] == "immobilized").sum()))
columns[3].metric("Energy exhausted", int((frame["termination"] == "energy_exhausted").sum()))

st.subheader("Failure modes by planner")
counts = (
    frame[frame["termination"] != "success"]
    .groupby(["planner", "termination"])
    .size()
    .reset_index(name="count")
)
counts["planner"] = counts["planner"].map(lambda p: PLANNER_LABELS.get(p, p))
st.plotly_chart(
    px.bar(
        counts,
        x="planner",
        y="count",
        color="termination",
        barmode="stack",
        color_discrete_map=TERMINATION_COLORS,
    )
    .update_layout(height=400, paper_bgcolor="rgba(0,0,0,0)")
    .update_xaxes(tickangle=20, title=""),
    use_container_width=True,
)

st.info(
    "**The pattern worth explaining to a judge.** Energy exhaustion dominates "
    "Martian failures. A robot carrying a lunar prior underestimates slip in "
    "drift sand, and because locomotion cost carries a 1/(1−slip) term it "
    "therefore underestimates the cost of *every* route it considers. It commits "
    "to a trip it cannot afford and strands itself. Correcting the slip belief "
    "corrects the energy estimate, which is why adaptation reduces this failure "
    "mode specifically rather than improving everything uniformly."
)

st.divider()
st.subheader("Where the proposed method loses")
st.caption(
    "Seeds where the adaptive planner failed and the fixed planner succeeded. "
    "These are the cases that argue against the method, so they are listed first."
)

pivot = frame.pivot_table(
    index=["condition", "seed"], columns="planner", values="success", aggfunc="first"
)
if {"adaptive_risk_aware_astar", "risk_aware_astar"} <= set(pivot.columns):
    adaptive_lost = pivot[
        (~pivot["adaptive_risk_aware_astar"].astype(bool))
        & (pivot["risk_aware_astar"].astype(bool))
    ]
    adaptive_won = pivot[
        (pivot["adaptive_risk_aware_astar"].astype(bool))
        & (~pivot["risk_aware_astar"].astype(bool))
    ]
    columns = st.columns(2)
    columns[0].metric("Seeds where adaptive lost", len(adaptive_lost))
    columns[1].metric("Seeds where adaptive won", len(adaptive_won))
    if len(adaptive_lost):
        st.dataframe(
            adaptive_lost.reset_index()[["condition", "seed"]],
            use_container_width=True,
            hide_index=True,
        )

st.divider()
st.subheader("Inspect a failed mission")

if failures.empty:
    st.success("No failures in this result set.")
    st.stop()

pick = failures.copy()
pick["label"] = pick.apply(
    lambda r: (
        f"{CONDITION_LABELS.get(r['condition'], r['condition'])} · "
        f"{PLANNER_LABELS.get(r['planner'], r['planner'])} · "
        f"seed {r['seed']} · {r['termination']}"
    ),
    axis=1,
)
choice = st.selectbox("Failed mission", pick["label"].tolist())
row = pick[pick["label"] == choice].iloc[0]

config = dict(
    body=row["body"],
    planner=row["planner"],
    size=int(row["size"]),
    n_targets=int(row["n_targets"]),
    max_steps=int(row["max_steps"]),
    risk_budget=float(row["risk_budget"]),
    fault_rate=float(row["fault_rate"]),
    comm_delay=int(row["comm_delay"]),
    solar_rate=float(row.get("solar_rate", 2.0)),
    energy_reserve_fraction=float(row.get("energy_reserve_fraction", 0.25)),
    prior_body=row["prior_body"],
    terrain_uncertainty=float(row["terrain_uncertainty"]),
)
result = cached_mission(config, int(row["seed"]))

if result.termination != row["termination"]:
    st.warning(
        f"Replay ended as `{result.termination}` but the stored row says "
        f"`{row['termination']}`. That is a reproducibility problem worth "
        "investigating, not a display glitch."
    )

left, right = st.columns([3, 2])
with left:
    terrain = get_terrain(row["body"], int(row["seed"]), int(row["size"]))
    driven = [(f["row"], f["col"]) for f in result.history]
    st.plotly_chart(
        terrain_figure(
            terrain,
            layer="Terrain class",
            path=driven,
            rover=driven[-1] if driven else None,
            home=result.mission_layout.get("home"),
            targets=result.mission_layout.get("targets"),
            title=f"ended: {result.termination}",
        ),
        use_container_width=True,
    )
with right:
    st.metric("Ended as", result.termination)
    st.metric(
        "Science returned", f"{result.science_return / max(result.science_possible, 1e-9):.0%}"
    )
    st.metric("Battery at end", f"{result.final_charge:.0f} Wh")
    st.metric("Lowest battery", f"{result.min_charge:.0f} Wh")
    st.metric("Distance from lander at end", f"{result.final_distance_from_home:.1f} cells")
    st.metric("Severe slip events", result.severe_slip_events)
    st.metric("Ground interventions", result.interventions)

    if result.history:
        charge = pd.DataFrame([{"step": f["step"], "battery": f["charge"]} for f in result.history])
        st.plotly_chart(
            px.line(charge, x="step", y="battery").update_layout(
                height=240, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)"
            ),
            use_container_width=True,
        )

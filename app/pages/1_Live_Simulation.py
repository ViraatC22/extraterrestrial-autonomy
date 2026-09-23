"""Watch one mission unfold, with the robot's beliefs beside its route."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from _shared import (  # noqa: E402
    CLASS_LABELS,
    LAYERS,
    PLANNER_LABELS,
    belief_figure,
    cached_mission,
    get_terrain,
    metric_row,
    page_setup,
    terrain_figure,
)
from exonaut.environments import TRUE_CLASS_PARAMS  # noqa: E402
from exonaut.experiments.protocol import load_splits  # noqa: E402

page_setup("Live Simulation")
st.title("Live Simulation")
st.caption(
    "One mission, replayed step by step. The rover starts at the lander, visits "
    "science targets, and tries to get home before its energy runs out."
)

splits = load_splits()

with st.sidebar:
    st.header("Mission")
    body = st.selectbox("Body", ["moon", "mars"], index=1)
    planner = st.selectbox(
        "Planner",
        list(PLANNER_LABELS),
        index=list(PLANNER_LABELS).index("adaptive_risk_aware_astar"),
        format_func=lambda k: PLANNER_LABELS[k],
    )
    split_name = st.selectbox(
        "Seed split",
        ["validation", "test", "ood", "train"],
        index=0,
        help="Validation is the safe one to explore interactively. Test and OOD "
        "seeds carry the confirmatory result; browsing them does not "
        "invalidate anything already published, but treat them as spent.",
    )
    seeds = splits.get(split_name)
    seed = st.select_slider("Terrain seed", options=list(seeds[:60]), value=seeds[0])

    st.divider()
    size = st.slider("Map size", 32, 80, 56, step=8)
    n_targets = st.slider("Science targets", 2, 8, 4)
    max_steps = st.slider("Step budget", 200, 1200, 600, step=100)
    risk_budget = st.slider(
        "Risk budget ε",
        0.02,
        0.60,
        0.20,
        step=0.02,
        help="Maximum tolerated P(mission failure) for a round trip.",
    )
    st.divider()
    fault_rate = st.slider("Expected faults", 0.0, 3.0, 0.0, step=0.5)
    comm_delay = st.slider("Comm delay (steps)", 0, 40, 0, step=5)

config = dict(
    body=body,
    planner=planner,
    size=size,
    n_targets=n_targets,
    max_steps=max_steps,
    risk_budget=risk_budget,
    fault_rate=fault_rate,
    comm_delay=comm_delay,
    solar_rate=2.0,
    energy_reserve_fraction=0.25,
    prior_body="moon",
)

result = cached_mission(config, seed)
terrain = get_terrain(body, seed, size)
frames = result.history

metric_row(result)
if body == "mars":
    st.caption(
        "This robot carries a **lunar** prior. On Mars the same terrain-class "
        "names carry different slip statistics — that mismatch is the domain "
        "shift under study."
    )

if not frames:
    st.warning("This mission produced no steps.")
    st.stop()

step_index = st.slider("Mission step", 1, len(frames), len(frames), step=1) - 1
frame = frames[step_index]

left, right = st.columns([3, 2])

with left:
    layer = st.selectbox("Map layer", list(LAYERS), index=0)
    driven = [(f["row"], f["col"]) for f in frames[: step_index + 1]]
    targets = []
    for target in result.mission_layout.get("targets", []):
        entry = dict(target)
        # a target counts as collected once the rover has stood on it
        entry["visited"] = (target["row"], target["col"]) in set(driven)
        targets.append(entry)

    st.plotly_chart(
        terrain_figure(
            terrain,
            layer=layer,
            path=driven,
            planned=frame["planned_path"],
            rover=(frame["row"], frame["col"]),
            home=result.mission_layout.get("home"),
            targets=targets,
        ),
        use_container_width=True,
    )

with right:
    st.metric("Battery", f"{frame['charge_fraction']:.0%}", f"{frame['charge']:.0f} Wh")
    status = "returning to lander" if frame["returning"] else "pursuing target"
    st.write(f"**Status** — {status}")
    if frame["goal"]:
        st.write(f"**Current goal** — {tuple(frame['goal'])}")
    st.write(f"**Science collected** — {frame['science']:.2f} ({frame['targets_visited']} targets)")
    st.write(f"**Ground interventions so far** — {frame['interventions']}")
    if frame["reason"] != "ok":
        st.warning(f"Last move blocked: `{frame['reason']}` (slip {frame['slip']:.2f})")

    st.divider()
    st.markdown("**Belief about terrain mobility**")
    adaptive = planner == "adaptive_risk_aware_astar"
    st.caption(
        "Dotted lines are the truth for this body. A fixed planner's lines stay "
        "flat by construction — only the adaptive planner revises them."
        if adaptive
        else "This planner does not revise its model, so these lines are flat. Switch "
        "to the adaptive planner to see them move."
    )
    true_values = {int(k): v.slip_mean for k, v in TRUE_CLASS_PARAMS[body].items()}
    st.plotly_chart(
        belief_figure(frames[: step_index + 1], true_values=true_values),
        use_container_width=True,
    )

    start, now = frames[0]["belief"], frame["belief"]
    moved = {k: now[k] - start[k] for k in now if abs(now[k] - start[k]) > 1e-6}
    if moved:
        biggest = max(moved, key=lambda k: abs(moved[k]))
        st.success(
            f"Largest revision: **{CLASS_LABELS.get(biggest, biggest)}** "
            f"{start[biggest]:.3f} → {now[biggest]:.3f} "
            f"(true {true_values.get(biggest, float('nan')):.3f})"
        )

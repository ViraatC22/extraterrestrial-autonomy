import time

import pandas as pd
import streamlit as st

from exonaut.experiments.runner import build_policy
from exonaut.multiagent.algorithms import available_algorithm_specs, display_name
from exonaut.multiagent.swarm_env import EnvConfig, SwarmEnv
from exonaut.viz.render import render_env

st.set_page_config(page_title="Live Simulation", page_icon="🛰️", layout="wide")
st.title("Live Simulation")
st.caption(
    "Gray = elevation. Pink overlay = explored by any rover. Red = hazard (steep slope / crater "
    "rim). Blue = permanently shadowed (no solar charging). Green lines = active mesh comm links."
)

specs = available_algorithm_specs()

with st.sidebar:
    st.header("Scenario")
    algo_name = st.selectbox("Algorithm", specs, format_func=display_name)
    seed = st.number_input("Terrain seed", min_value=0, max_value=10_000, value=1)
    terrain_size = st.slider("Terrain size (cells/side)", 24, 96, 48, step=8)
    n_rovers = st.slider("Swarm size", 1, 8, 4)
    comm_radius = st.slider("Communication radius (cells)", 1, 60, 12)
    sensor_radius = st.slider("Sensor radius (cells)", 1, 10, 4)
    failure_rate = st.slider("Rover failure rate", 0.0, 1.0, 0.0, step=0.05)
    max_steps = st.slider("Max steps", 50, 800, 250, step=25)
    speed = st.select_slider("Steps per tick (autoplay)", options=[1, 2, 4, 8, 16], value=4)

    reset_clicked = st.button("Reset scenario", width="stretch")
    step_clicked = st.button("Step once", width="stretch")
    autoplay = st.toggle("Autoplay", value=False)

new_config = dict(
    terrain_size=terrain_size,
    n_rovers=n_rovers,
    comm_radius=comm_radius,
    sensor_radius=sensor_radius,
    failure_rate=failure_rate,
    max_steps=max_steps,
    seed=seed,
)
needs_reset = (
    reset_clicked
    or "live_env" not in st.session_state
    or st.session_state.get("live_env_config") != new_config
    or st.session_state.get("live_env_algo") != algo_name
)

if needs_reset:
    st.session_state["live_env"] = SwarmEnv(EnvConfig(**new_config))
    st.session_state["live_env_config"] = new_config
    st.session_state["live_env_algo"] = algo_name
    st.session_state["live_policy"] = build_policy(algo_name)

env: SwarmEnv = st.session_state["live_env"]
policy = st.session_state["live_policy"]


def do_step() -> None:
    if not env.done:
        actions = {rid: policy(env, rid) for rid in env.rover_ids}
        env.step(actions)


if step_clicked:
    do_step()

col1, col2 = st.columns([2, 1])

with col1:
    fig = render_env(env)
    st.pyplot(fig, width="stretch")

with col2:
    coverage_frac = float(env.coverage[~env.terrain.hazard_mask].mean())
    alive = sum(1 for r in env.rovers if r.alive)
    st.metric("Step", f"{env.step_count} / {env.config.max_steps}")
    st.metric("Coverage", f"{coverage_frac * 100:.1f}%")
    st.metric("Rovers alive", f"{alive}/{len(env.rovers)}")
    if env.done:
        st.success("Episode finished.")

    if env.history:
        hist_df = pd.DataFrame(env.history).set_index("step")
        st.caption("Coverage over time")
        st.line_chart(hist_df[["coverage"]])
        st.caption("Mean battery over time")
        st.line_chart(hist_df[["mean_battery"]])

if autoplay and not env.done:
    for _ in range(speed):
        do_step()
        if env.done:
            break
    time.sleep(0.05)
    st.rerun()

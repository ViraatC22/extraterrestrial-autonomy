import streamlit as st

st.set_page_config(page_title="Lunar Swarm Nav", page_icon="🌑", layout="wide")

st.title("🌑 Lunar Swarm Nav")
st.subheader("Decentralized vs. learned swarm coordination for communication-constrained lunar surface exploration")

st.markdown(
    """
**Motivation.** NASA's [CADRE mission](https://www.jpl.nasa.gov/missions/cadre/) will land three
autonomous rovers on the Moon in 2026 that navigate, communicate over a mesh network, and make
decisions cooperatively with no real-time human input — because Earth-Moon communication has
latency and dropout that rules out remote-control. This project asks: **when the communication
range between rovers shrinks, how much better does a *learned* decentralized coordination policy
do at exploring the terrain than classical swarm algorithms — and how much more resilient is it
when rovers fail?**

**Hypothesis.** A swarm of rovers using a lightweight policy trained with reinforcement learning
(acting only on each rover's own sensed map plus whatever it has received over a range-limited
mesh network) will achieve significantly higher terrain coverage per unit of energy spent, and
degrade more gracefully when rovers are lost, than classical baselines — frontier-based greedy
exploration, artificial potential fields, and ant-colony-style stigmergy — and that this advantage
grows as communication range shrinks.

**What's in this app:**
- **Live Simulation** — watch a single run of any algorithm on procedurally generated lunar
  terrain (craters, hazard slopes, permanently shadowed regions), step by step.
- **Run Experiments** — configure and run a full statistical sweep: every algorithm across a grid
  of communication radii, swarm sizes, and rover-failure rates, repeated across many random seeds.
- **Results Explorer** — summary statistics, distribution plots, and ANOVA / pairwise t-tests on
  any saved sweep.

See [`docs/METHODOLOGY.md`](https://github.com/ViraatC22/lunar-swarm-nav/blob/master/docs/METHODOLOGY.md)
for the full experimental design, and
[`docs/REFERENCES.md`](https://github.com/ViraatC22/lunar-swarm-nav/blob/master/docs/REFERENCES.md)
for the research this project builds on.
"""
)

st.info("Use the sidebar to navigate between pages.")

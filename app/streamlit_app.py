"""EXONAUT dashboard — home page."""

import streamlit as st  # noqa: E402

from _shared import DOCS_DIR, page_setup  # noqa: E402

page_setup("Home")

st.title("EXONAUT")
st.subheader(
    "Adaptive risk-aware autonomy for robotic exploration of uncertain extraterrestrial terrain"
)

left, right = st.columns([3, 2])

with left:
    st.markdown(
        """
### The problem

A planetary rover cannot be driven in real time from Earth. Round-trip light
time to Mars runs from roughly eight to forty minutes, and contact windows are
intermittent, so by the time an operator sees a problem the problem has already
happened. The robot has to decide for itself which ground is safe to cross.

Those decisions rest on a terrain model built **before launch**, from whatever
experience was available at the time.

### The failure mode that actually matters

Planetary rovers are not usually lost by driving off cliffs. They are lost by
**sinking**. A rover crossing ground that looks flat and benign can lose
traction in loose material, dig itself in, and become permanently immobile —
which is how NASA's *Spirit* ended its driving mission in 2009.

This is hard for autonomy because it is invisible to geometry. The ground that
traps a rover is often perfectly flat. Detecting it needs a model of how terrain
*behaves*, not how it *looks*.

### The asymmetry this project is built around

- **Geometry** — slope, roughness, obstacles — can be sensed at a distance.
- **Mobility** can only be measured by committing the vehicle to the ground.

So a robot plans long routes using a model it cannot verify in advance, and the
model it started with was calibrated somewhere else.

### The research question

> Does a planetary robot that continuously updates its terrain-mobility model
> from its own driving make safer and more productive decisions than one using
> a fixed model, when the terrain it meets does not match the model it was given?
"""
    )

with right:
    st.info(
        """
**What is compared**

Five planners over one identical simulator, differing only in the cost they
assign and whether its inputs are revised:

- Distance-only A\\*
- Dijkstra (heuristic control)
- D\\* Lite (incremental replanning)
- Fixed risk-aware A\\*
- **Adaptive risk-aware A\\*** — the proposed method

The adaptive planner is a subclass of the fixed one overriding a single
method, so a measured difference is attributable to that one switch.
"""
    )
    st.warning(
        """
**Scope, stated plainly**

This is a controlled 2.5-D testbed for comparing *decision rules*. It is not a
validated dynamics model of any flight vehicle or landing site, and its
absolute numbers are properties of the model rather than predictions of
on-surface performance.
"""
    )
    st.success(
        """
**Headline result**

Adaptation was **neutral in-distribution** and did **not** improve science
return under domain shift — contradicting our own hypothesis H2.

What survived correction: mission success under hardware faults rose
**0.26 → 0.46**, winning all ten seeds on which the planners differed.

Adaptation bought **survival, not productivity**.
"""
    )

st.divider()
st.markdown("#### Pages")
columns = st.columns(3)
columns[0].markdown(
    "**Live Simulation** — watch one mission unfold, step by step, with the "
    "robot's beliefs updating beside its route.\n\n"
    "**Scenario Lab** — change terrain, uncertainty, energy and faults, and "
    "see what breaks."
)
columns[1].markdown(
    "**Algorithm Comparison** — run every planner on the *same* terrain and "
    "compare their routes directly.\n\n"
    "**Results** — the confirmatory statistics on held-out seeds."
)
columns[2].markdown(
    "**Failure Analysis** — the missions that failed, and why.\n\n"
    "**Planetary Data** — how real orbital terrain would slot in, and what is "
    "not yet implemented."
)

with st.expander("Scientific integrity notes — read before quoting any number"):
    st.markdown(
        """
- Terrain seeds are split into disjoint **train / validation / test / OOD**
  sets, frozen to a checksummed file. Priors are calibrated on train seeds;
  all tuning used validation seeds; test and OOD informed no design decision.
- Eight seeds consumed by an early engineering pilot are **permanently
  quarantined** and cannot appear in any confirmatory result. CI asserts this.
- `docs/PREREGISTRATION.md` is a **confirmatory analysis plan, not a
  pre-registration** — it was written after the adaptive planner existed. The
  full timeline is in `docs/RESEARCH_LOG.md`.
- The validation-set advantage that motivated H2 (+0.125 to +0.167 in Martian
  success) **did not replicate** on held-out seeds. That is the strongest
  argument in this project for having frozen the splits before tuning.
"""
    )

if (DOCS_DIR / "RESULTS.md").exists():
    with st.expander("docs/RESULTS.md"):
        st.markdown((DOCS_DIR / "RESULTS.md").read_text())

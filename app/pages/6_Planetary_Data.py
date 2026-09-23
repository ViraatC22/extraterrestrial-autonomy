"""Real orbital terrain — what is implemented and what is not."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from _shared import LAYERS, get_terrain, page_setup, terrain_figure  # noqa: E402
from exonaut.environments import TRUE_CLASS_PARAMS  # noqa: E402

page_setup("Planetary Data")
st.title("Real Planetary Data")

st.error(
    "**Not yet implemented.** No mission-derived terrain is used anywhere in "
    "this project. Every result comes from procedurally generated terrain. This "
    "page documents how real data would be incorporated and what would have to "
    "be verified first — it does not show real data, and nothing in the paper "
    "depends on it."
)

st.markdown(
    """
### Why it is not claimed

The simulator is a controlled testbed for comparing decision rules, not a
validated model of any landing site. Its terrain parameters were chosen to
produce the qualitative regimes the experiment needs — a low-traction trap, a
high-traction refuge, impassable rims, and true darkness — and are **not**
calibrated against measured lunar or Martian geotechnical data.

Presenting procedural terrain as though it were mission data would be the
single most damaging thing this project could do to its own credibility, so
the distinction is kept explicit in the code, the paper, and here.

### How real terrain would slot in

The environment layer already separates *terrain content* from *terrain
semantics*. A `TerrainField` is just a set of aligned rasters plus a per-class
parameter table:

```
elevation   →  slope (gradient magnitude)
roughness   →  terrain-class assignment
illumination
hazard mask
class parameters: slip mean, slip dispersion, energy multiplier
```

A real digital elevation model supplies `elevation` directly; slope is derived
the same way it already is. That means swapping in mission data is a loader
problem, not a redesign.

Candidate sources:

| Source | Provides | Approximate scale |
|---|---|---|
| LRO LOLA | Lunar global topography | 60–120 m/px |
| LRO NAC | Lunar high-resolution imagery | 0.5–2 m/px |
| MOLA | Mars global topography | ~463 m/px |
| HiRISE / HRSC DTMs | Mars local elevation models | 1–20 m/px |

### What would have to be settled first, honestly

1. **Resolution mismatch.** This simulator treats one cell as roughly one
   metre of rover travel. Most global DEMs are far coarser, so a naive load
   would produce terrain that is smooth at rover scale and would make every
   planner look better than it should.
2. **Terrain class is not observable from a DEM.** Slip behaviour is the thing
   that matters here, and it cannot be read off elevation. Assigning classes
   from orbital imagery would need a perception model, which is a separate
   project and would need its own validation.
3. **The class parameters would still be invented.** Even with real geometry,
   the slip statistics that drive every result would remain uncalibrated
   unless tied to published terramechanics or to rover telemetry. Real
   elevation plus invented mobility would look more credible without being
   more credible, which is worse than the current position.

Until at least (2) and (3) are addressed, adding real DEMs would change the
appearance of this project rather than its evidence.

### What is used instead
"""
)

columns = st.columns(2)
with columns[0]:
    body = st.selectbox("Body", ["moon", "mars"])
    seed = st.number_input("Seed", value=200000, step=1)
    size = st.slider("Size", 32, 96, 64, step=8)
    layer = st.selectbox("Layer", list(LAYERS))
terrain = get_terrain(body, int(seed), int(size))
with columns[1]:
    st.markdown("**True per-class mobility for this body**")
    parameters = TRUE_CLASS_PARAMS[body]
    st.dataframe(
        [
            {
                "class": p.label,
                "mean slip": p.slip_mean,
                "dispersion": p.slip_dispersion,
                "energy multiplier": p.energy_multiplier,
            }
            for p in parameters.values()
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "These are the numbers the robot must discover by driving. They are "
        "model parameters, not measurements."
    )

st.plotly_chart(terrain_figure(terrain, layer=layer, height=560), use_container_width=True)

st.caption(
    f"Procedural {body} terrain, seed {seed}. Fully reproducible from the seed "
    "alone — which is what makes the paired experimental design possible, and is "
    "a property real mission data would not have."
)

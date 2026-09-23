"""The confirmatory statistics, read straight from the committed results."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json  # noqa: E402

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from _shared import (  # noqa: E402
    CONDITION_LABELS,
    PLANNER_LABELS,
    RESULTS_DIR,
    TERMINATION_COLORS,
    available_result_sets,
    load_results,
    page_setup,
)
from exonaut.experiments.analysis import (  # noqa: E402
    descriptive_table,
    generalization_gap,
    primary_analysis,
    secondary_analysis,
)

page_setup("Results")
st.title("Results")

sets = available_result_sets()
if not sets:
    st.warning("No result files found. Run `scripts/run_exonaut_experiments.py`.")
    st.stop()

default = sets.index("exonaut_main") if "exonaut_main" in sets else 0
name = st.selectbox("Result set", sets, index=default)
frame = load_results(name)

meta_path = RESULTS_DIR / f"{name}.metadata.json"
if meta_path.exists():
    meta = json.loads(meta_path.read_text())
    git = meta.get("git", {}) or {}
    columns = st.columns(4)
    columns[0].metric("Missions", len(frame))
    columns[1].metric("Seeds / condition", meta.get("n_seeds_per_condition", "?"))
    columns[2].metric("Commit", (git.get("commit") or "?")[:8])
    columns[3].metric("Split checksum", (meta.get("seed_split_checksum") or "?")[:8])
    if meta.get("quarantined_seeds"):
        st.caption(
            f"Quarantined seeds excluded from this run: {json.dumps(meta['quarantined_seeds'])}"
        )
    if git.get("dirty_worktree"):
        st.caption(
            "Worktree was dirty when this ran — see docs/REPRODUCIBILITY.md for "
            "what that does and does not imply."
        )

if name != "exonaut_main":
    st.warning(
        "This is not the confirmatory result set. The pilot in particular "
        "predates the defect fixes recorded in docs/RESEARCH_LOG.md and is "
        "retained only as a historical record."
    )

st.divider()
st.subheader("Outcomes by condition")

descriptive = descriptive_table(frame)
descriptive["condition_label"] = descriptive["condition"].map(lambda c: CONDITION_LABELS.get(c, c))
descriptive["planner_label"] = descriptive["planner"].map(lambda p: PLANNER_LABELS.get(p, p))

metric = st.radio(
    "Outcome",
    ["success_rate", "science_fraction", "interventions", "severe_slip_events"],
    horizontal=True,
)
st.plotly_chart(
    px.bar(
        descriptive,
        x="condition_label",
        y=metric,
        color="planner_label",
        barmode="group",
        labels={
            "condition_label": "",
            metric: metric.replace("_", " "),
            "planner_label": "planner",
        },
    ).update_layout(
        height=430,
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    ),
    use_container_width=True,
)

st.dataframe(
    descriptive[
        [
            "condition_label",
            "planner_label",
            "n",
            "success_rate",
            "science_fraction",
            "immobilized",
            "energy_exhausted",
            "timeout",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)

st.subheader("How missions ended")
termination = (
    frame.groupby(["condition", "planner", "termination"]).size().reset_index(name="count")
)
termination["condition_label"] = termination["condition"].map(lambda c: CONDITION_LABELS.get(c, c))
termination["planner_label"] = termination["planner"].map(lambda p: PLANNER_LABELS.get(p, p))
st.plotly_chart(
    px.bar(
        termination,
        x="planner_label",
        y="count",
        color="termination",
        facet_col="condition_label",
        barmode="stack",
        color_discrete_map=TERMINATION_COLORS,
    )
    .update_layout(height=420, paper_bgcolor="rgba(0,0,0,0)")
    .update_xaxes(tickangle=40, title="")
    .for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1], font_size=10)),
    use_container_width=True,
)

st.divider()
st.subheader("Primary contrasts — adaptive vs fixed risk-aware")
st.caption(
    "Paired within condition and seed, Holm-corrected across the primary family. "
    "Mission success is binary and paired, so it uses McNemar's exact test on the "
    "seeds where the planners actually disagreed."
)

primary = primary_analysis(frame)
if primary.empty:
    st.info("Not enough matched data for the primary contrasts.")
else:
    display = primary.copy()
    display["condition"] = display["condition"].map(lambda c: CONDITION_LABELS.get(c, c))
    columns = [
        "condition",
        "metric",
        "mean_control",
        "mean_treatment",
        "mean_diff",
        "ci95_low",
        "ci95_high",
        "p_value",
        "p_holm",
        "significant",
        "test",
    ]
    if "p_bootstrap" in display.columns:
        columns.insert(-2, "p_bootstrap")
    st.dataframe(display[columns], use_container_width=True, hide_index=True)

    survivors = display[display["significant"]]
    if len(survivors):
        for _, row in survivors.iterrows():
            st.success(
                f"**{row['condition']} — {row['metric']}**: "
                f"Δ = {row['mean_diff']:+.3f} "
                f"[{row['ci95_low']:+.3f}, {row['ci95_high']:+.3f}], "
                f"p_Holm = {row['p_holm']:.3f}"
            )
    else:
        st.info("No contrast in the primary family survives Holm correction.")

with st.expander("Secondary contrasts (against distance-only A*)"):
    secondary = secondary_analysis(frame)
    if secondary.empty:
        st.info("Not available.")
    else:
        secondary["condition"] = secondary["condition"].map(lambda c: CONDITION_LABELS.get(c, c))
        st.dataframe(secondary, use_container_width=True, hide_index=True)
        st.caption(
            "Corrected separately from the primary family so they cannot inflate its error rate."
        )

st.subheader("Generalization gap")
gap = generalization_gap(frame)
if not gap.empty:
    gap["planner"] = gap["planner"].map(lambda p: PLANNER_LABELS.get(p, p))
    st.dataframe(gap, use_container_width=True, hide_index=True)
    st.caption(
        "G = in-distribution minus out-of-distribution. This ranking is **not** "
        "informative here: G is a difference, so it mechanically rewards planners "
        "that perform poorly in distribution. Reported for completeness."
    )

st.divider()
with st.expander("Verdict against the stated hypotheses"):
    st.markdown(
        """
- **H1 — supported.** Lunar parity between adaptive and fixed.
- **H2 — not supported.** Martian science fraction moved *against* the
  hypothesis and Martian success was exactly tied. The validation-set advantage
  did not replicate on held-out seeds.
- **H3 — partially supported.** Success under injected faults rose, the only
  contrast surviving Holm correction; adaptation won every discordant seed.
- **H4 —** reported descriptively above.

Reporting a failed primary hypothesis is the point of fixing the analysis plan
in advance. Had the seed splits not been frozen before tuning, the
validation-set figure is the one that would have been published.
"""
    )

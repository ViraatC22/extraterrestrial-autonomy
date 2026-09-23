import pandas as pd
import plotly.express as px
import streamlit as st

from exonaut.experiments.runner import RESULTS_DIR
from exonaut.experiments.stats import (
    paired_comparisons,
    repeated_measures_anova,
    summarize,
    two_way_anova,
)

st.set_page_config(page_title="Results Explorer", page_icon="📊", layout="wide")
st.title("Results Explorer")

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
csv_files = sorted(p.name for p in RESULTS_DIR.glob("*.csv"))

if not csv_files:
    st.info("No experiment results yet. Run a sweep on the **Run Experiments** page first.")
    st.stop()

selected = st.selectbox("Results file", csv_files, index=len(csv_files) - 1)
df = pd.read_csv(RESULTS_DIR / selected)
st.caption(f"{len(df)} trials loaded from `{selected}`")

metric = st.selectbox(
    "Metric", ["final_coverage", "coverage_per_energy", "energy_spent", "rovers_alive", "steps_taken"],
)
group_col = st.selectbox("Group by", ["algorithm", "comm_radius", "n_rovers", "failure_rate"])

st.subheader("Summary")
st.dataframe(summarize(df, metric=metric, group_cols=(group_col,)), width="stretch")

st.subheader("Distribution")
color = "algorithm" if group_col != "algorithm" else None
fig = px.box(df, x=group_col, y=metric, color=color, points="all")
st.plotly_chart(fig, width="stretch")

if "comm_radius" in df.columns and df["comm_radius"].nunique() > 1:
    st.subheader(f"{metric} vs. communication radius, by algorithm")
    line_df = df.groupby(["algorithm", "comm_radius"])[metric].mean().reset_index()
    fig2 = px.line(line_df, x="comm_radius", y=metric, color="algorithm", markers=True)
    st.plotly_chart(fig2, width="stretch")

st.subheader("Statistics")
if df["algorithm"].nunique() < 2:
    st.info("Need at least two algorithms in this results file to run comparison statistics.")
else:
    st.caption(
        "Every algorithm is run on the same terrain seeds, so these are *paired* "
        "(randomized block) analyses — matching each algorithm's trial to the other "
        "algorithms' trials on the identical terrain removes between-terrain variance."
    )

    anova = repeated_measures_anova(df, metric=metric)
    if "error" in anova:
        st.warning(anova["error"])
    else:
        verdict = "statistically significant" if anova["significant"] else "not statistically significant"
        st.markdown(
            f"**Repeated-measures ANOVA** on `{metric}`: "
            f"F({anova['df_treatment']}, {anova['df_error']}) = {anova['f_stat']:.3f}, "
            f"p = {anova['p_value']:.4g}, partial η² = {anova['partial_eta_squared']:.3f} "
            f"— {verdict} at α = 0.05, over {anova['n_blocks']} matched blocks."
        )

    st.caption(
        "Pairwise paired t-tests with Holm–Bonferroni correction across the family of "
        "comparisons. `cohens_dz` is the paired effect size; `p_wilcoxon` is a "
        "non-parametric companion test."
    )
    st.dataframe(paired_comparisons(df, metric=metric), width="stretch")

    if "comm_radius" in df.columns and df["comm_radius"].nunique() > 1:
        st.caption(
            "Factorial ANOVA — the interaction row tests whether the gap between "
            "algorithms *changes* with communication radius."
        )
        st.dataframe(two_way_anova(df, metric=metric), width="stretch")

st.download_button(
    "Download this results CSV", df.to_csv(index=False), file_name=selected, mime="text/csv",
)

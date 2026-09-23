import streamlit as st

from lunar_swarm.algorithms import build_algorithm_registry
from lunar_swarm.experiments.runner import run_sweep

st.set_page_config(page_title="Run Experiments", page_icon="🧪", layout="wide")
st.title("Run Experiments")
st.markdown(
    """
Configure a batch sweep across algorithms and experimental conditions. Every
(algorithm, condition, seed) combination is one independent trial on freshly
generated terrain — that's what makes the comparison statistically
meaningful rather than anecdotal. Results are saved as a CSV under
`data/results/` and can be analyzed on the **Results Explorer** page.
"""
)

registry = build_algorithm_registry()

with st.form("sweep_form"):
    algo_names = st.multiselect(
        "Algorithms to compare", list(registry.keys()), default=list(registry.keys()),
    )
    comm_radii = st.multiselect(
        "Communication radii to test (cells)", [3, 6, 10, 16, 24, 40], default=[6, 16, 40],
    )
    n_rovers_list = st.multiselect(
        "Swarm sizes to test", [1, 2, 4, 6, 8], default=[4],
    )
    failure_rates = st.multiselect(
        "Rover failure rates to test", [0.0, 0.25, 0.5], default=[0.0, 0.25],
    )
    n_seeds = st.slider("Trials per condition (random seeds)", 3, 30, 8)
    terrain_size = st.slider("Terrain size (cells/side)", 24, 96, 48, step=8)
    max_steps = st.slider("Max steps per trial", 50, 600, 250, step=25)
    save_name = st.text_input("Save results as", value="sweep_results.csv")
    submitted = st.form_submit_button("Run sweep", width="stretch")

if submitted:
    if not algo_names or not comm_radii or not n_rovers_list or not failure_rates:
        st.error("Pick at least one option in every field.")
        st.stop()

    n_trials = len(algo_names) * len(comm_radii) * len(n_rovers_list) * len(failure_rates) * n_seeds
    st.caption(f"Running {n_trials} trials...")
    progress = st.progress(0.0)
    status = st.empty()

    def _progress_cb(done, total, algo_name, env_kwargs, seed):
        progress.progress(done / total)
        status.text(f"{done}/{total} — {algo_name}, {env_kwargs}, seed={seed}")

    algorithms = {name: registry[name] for name in algo_names}
    df = run_sweep(
        algorithms=algorithms,
        comm_radii=comm_radii,
        n_rovers_list=n_rovers_list,
        failure_rates=failure_rates,
        n_seeds=n_seeds,
        base_kwargs=dict(terrain_size=terrain_size, max_steps=max_steps),
        save_as=save_name,
        progress_cb=_progress_cb,
    )
    status.text(f"Done — {len(df)} trials.")
    st.success(f"Ran {len(df)} trials and saved to data/results/{save_name}")
    st.dataframe(df, width="stretch")

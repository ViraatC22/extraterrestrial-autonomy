"""Central registry combining classical baselines with any trained RL
models found under models/, so the Streamlit app and experiment scripts
discover the same set of algorithms without duplicating logic."""
from __future__ import annotations

from pathlib import Path

from .baselines import BASELINES

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


def discover_rl_models() -> dict[str, Path]:
    if not MODELS_DIR.exists():
        return {}
    return {p.stem: p for p in sorted(MODELS_DIR.glob("*.zip"))}


def build_algorithm_registry(include_rl: bool = True) -> dict:
    """Returns {name: policy_spec}. Classical baselines are returned as-is
    (functions, or classes for the runner to instantiate per trial). RL
    models are eagerly loaded (torch import + model deserialization), so
    only call this once per script/session rather than per trial."""
    registry: dict = dict(BASELINES)
    if include_rl:
        from .rl.rl_policy import RLPolicy  # deferred: heavy torch import
        for name, path in discover_rl_models().items():
            registry[f"rl:{name}"] = RLPolicy(path)
    return registry

"""Discovery of the algorithms available to evaluate.

Algorithms are referred to by short string specs ("frontier",
"rl:models/ppo_seed0.zip") so they can be passed to worker processes and
recorded verbatim in the results CSV - every row states exactly which
policy, and for RL exactly which checkpoint, produced it.
"""

from __future__ import annotations

from pathlib import Path

from .baselines import BASELINES

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"

BASELINE_SPECS = list(BASELINES.keys())

DISPLAY_NAMES = {
    "frontier": "Frontier (greedy nearest-frontier)",
    "potential_field": "Artificial potential field",
    "pheromone": "Pheromone stigmergy (ACO-style)",
}


def discover_rl_specs() -> list[str]:
    """Every trained checkpoint under models/, as run-ready specs."""
    if not MODELS_DIR.exists():
        return []
    specs = []
    for path in sorted(MODELS_DIR.glob("*.zip")):
        rel = path.relative_to(PROJECT_ROOT)
        specs.append(f"rl:{rel.as_posix()}")
    return specs


def available_algorithm_specs(include_rl: bool = True) -> list[str]:
    specs = list(BASELINE_SPECS)
    if include_rl:
        specs.extend(discover_rl_specs())
    return specs


def display_name(spec: str) -> str:
    if spec.startswith("rl:"):
        return f"RL policy ({Path(spec[3:]).stem})"
    return DISPLAY_NAMES.get(spec, spec)

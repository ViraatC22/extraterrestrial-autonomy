import pytest

from exonaut.multiagent.baselines import BASELINES
from exonaut.multiagent.swarm_env import EnvConfig, SwarmEnv


@pytest.mark.parametrize("name", list(BASELINES.keys()))
@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_baseline_makes_meaningful_progress(name, seed):
    """Regression test for a real bug found during development: a policy
    that always takes the single best-matching direction toward its target
    can get permanently wedged the moment that heading points at a hazard
    cell, producing near-zero coverage regardless of algorithm. Every
    baseline should reliably explore a substantial fraction of the map
    within a short episode on a variety of terrains."""
    policy_spec = BASELINES[name]
    cfg = EnvConfig(terrain_size=32, n_rovers=3, max_steps=120, seed=seed, comm_radius=10)
    env = SwarmEnv(cfg)
    policy = policy_spec() if isinstance(policy_spec, type) else policy_spec
    while not env.done:
        actions = {rid: policy(env, rid) for rid in env.rover_ids}
        env.step(actions)
    coverage = float(env.coverage[~env.terrain.hazard_mask].mean())
    assert coverage > 0.1, f"{name} only reached {coverage:.3f} coverage on seed {seed} (likely stuck)"


@pytest.mark.parametrize("name", list(BASELINES.keys()))
def test_baseline_never_crashes_with_failures_and_small_comm_radius(name):
    policy_spec = BASELINES[name]
    cfg = EnvConfig(terrain_size=32, n_rovers=5, max_steps=80, seed=9, comm_radius=2, failure_rate=0.4)
    env = SwarmEnv(cfg)
    policy = policy_spec() if isinstance(policy_spec, type) else policy_spec
    while not env.done:
        actions = {rid: policy(env, rid) for rid in env.rover_ids}
        env.step(actions)
    assert env.done

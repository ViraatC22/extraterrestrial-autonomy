import numpy as np

from exonaut.multiagent.rl.policy_env import OBS_DIM, SingleRoverTrainingEnv
from exonaut.multiagent.swarm_env import EnvConfig


def test_reset_and_step_shapes():
    env = SingleRoverTrainingEnv(EnvConfig(terrain_size=24, n_rovers=2, max_steps=30, seed=1))
    obs, info = env.reset(seed=1)
    assert obs.shape == (OBS_DIM,)
    assert np.all(obs >= -1.0) and np.all(obs <= 1.0)

    obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
    assert obs.shape == (OBS_DIM,)
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)


def test_episode_eventually_ends():
    env = SingleRoverTrainingEnv(EnvConfig(terrain_size=24, n_rovers=2, max_steps=15, seed=2))
    env.reset(seed=2)
    done = False
    steps = 0
    while not done and steps < 200:
        _, _, terminated, truncated, _ = env.step(env.action_space.sample())
        done = terminated or truncated
        steps += 1
    assert done
    assert steps <= 15

import pytest

from lunar_swarm.environment import EnvConfig, SwarmEnv
from lunar_swarm.rover import STAY_ACTION


def make_env(**overrides):
    defaults = dict(terrain_size=32, n_rovers=4, max_steps=60, seed=1)
    defaults.update(overrides)
    return SwarmEnv(EnvConfig(**defaults))


def test_rovers_spawn_on_distinct_traversable_cells():
    env = make_env()
    positions = [r.pos for r in env.rovers]
    assert len(set(positions)) == len(positions)
    for r in env.rovers:
        assert env.terrain.is_traversable(r.row, r.col, r.max_slope_deg)


def test_coverage_never_decreases():
    env = make_env()
    prev = 0.0
    for _ in range(30):
        actions = {rid: STAY_ACTION for rid in env.rover_ids}
        env.step(actions)
        cur = float(env.coverage[~env.terrain.hazard_mask].mean())
        assert cur >= prev - 1e-9
        prev = cur


def test_staying_still_only_costs_idle_battery():
    env = make_env(n_rovers=1)
    rover = env.rovers[0]
    start_battery = rover.battery
    env.step({rover.rover_id: STAY_ACTION})
    # idle cost is small; battery should barely move (solar may offset it too)
    assert abs(rover.battery - start_battery) < 1.0


def test_episode_terminates_within_max_steps():
    env = make_env(max_steps=25)
    steps = 0
    while not env.done and steps < 1000:
        actions = {rid: STAY_ACTION for rid in env.rover_ids}
        env.step(actions)
        steps += 1
    assert env.done
    assert steps <= 25


def test_energy_spent_is_cumulative_not_battery_deficit():
    """Solar recharge means end-of-episode battery level understates energy
    expenditure; energy_spent must track the true cumulative draw."""
    from lunar_swarm.baselines import frontier_policy

    env = make_env(n_rovers=2, max_steps=60)
    while not env.done:
        env.step({rid: frontier_policy(env, rid) for rid in env.rover_ids})

    for rover in env.rovers:
        assert rover.energy_spent > 0
        battery_deficit = 100.0 - rover.battery
        # any rover that recharged at all spent strictly more than its deficit
        assert rover.energy_spent >= battery_deficit - 1e-9

    m = env.metrics()
    assert m["energy_spent"] == pytest.approx(sum(r.energy_spent for r in env.rovers))
    assert m["coverage_per_energy"] == pytest.approx(
        m["final_coverage"] / m["energy_spent"]
    )


def test_energy_spent_matches_action_costs():
    from lunar_swarm.rover import DIAGONAL_COST, IDLE_COST, MOVE_COST, STAY_ACTION

    env = make_env(n_rovers=1, max_steps=50)
    rover = env.rovers[0]
    env.step({rover.rover_id: STAY_ACTION})
    assert rover.energy_spent == pytest.approx(IDLE_COST)

    before_pos = rover.pos
    before_energy = rover.energy_spent
    env.step({rover.rover_id: 0})  # attempt a north move
    delta = rover.energy_spent - before_energy
    if rover.pos != before_pos:
        assert delta == pytest.approx(MOVE_COST)  # axial move
    else:
        assert delta == pytest.approx(IDLE_COST)  # blocked, charged as idle
    assert DIAGONAL_COST == pytest.approx(2 ** 0.5)


def test_failure_injection_reduces_alive_count():
    env = make_env(n_rovers=6, failure_rate=0.5, failure_step_frac=0.1, max_steps=40)
    while not env.done:
        actions = {rid: STAY_ACTION for rid in env.rover_ids}
        env.step(actions)
    alive = sum(1 for r in env.rovers if r.alive)
    assert alive < len(env.rovers)

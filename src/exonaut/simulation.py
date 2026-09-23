"""The mission simulation loop.

One `run_mission()` call is one complete trial: a robot starts at a lander,
tries to visit science targets, and tries to get home before its energy runs
out, while the terrain behaves differently from what it expected and its own
hardware occasionally degrades.

Everything a trial does is determined by `MissionConfig` plus its seed, so
the same configuration and seed always produce the same mission - including
the terrain, the target layout, the fault schedule, and every slip draw. That
determinism is what lets different planners be compared on genuinely
identical worlds.

Communication delay is modeled where it actually bites for a single distant
robot: when the autonomy stack cannot find any route it believes in, it has
to stop and ask mission control. The robot then idles for `comm_delay` steps
before receiving a relaxed instruction. Every such episode is counted as a
human intervention, which is itself a headline metric - an autonomy system
that succeeds only by phoning home constantly has not really succeeded.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from .autonomy.mission_manager import MissionManager, generate_mission
from .autonomy.world_model import AdaptiveWorldModel, WorldModel
from .environments import TRUE_CLASS_PARAMS, make_environment
from .robot import FaultSchedule, Rover, SensorSuite
from .robot.power import PowerSystem

TERMINATION_SUCCESS = "success"
TERMINATION_IMMOBILIZED = "immobilized"
TERMINATION_ENERGY = "energy_exhausted"
TERMINATION_TIMEOUT = "timeout"

#: Nominal battery capacity at lunar gravity; scaled by gravity per body.
BASE_BATTERY_CAPACITY = 180.0


@dataclass
class MissionConfig:
    body: str = "moon"
    planner: str = "risk_aware_astar"
    size: int = 64
    n_targets: int = 5
    max_steps: int = 600
    risk_budget: float = 0.20
    # Fraction of battery capacity held back as contingency. A fraction, not
    # an absolute figure: capacity is scaled by gravity per body, so a fixed
    # 12 Wh reserve was 6.7% of the lunar battery but only 2.9% of the Martian
    # one - the robot kept almost no margin exactly where it needed the most.
    energy_reserve_fraction: float = 0.25
    sensing_radius: int = 6
    sensor_noise_scale: float = 1.0
    terrain_uncertainty: float = 1.0  # multiplies true slip dispersion
    # None = size the power system for the body, the way a real mission would
    # (a Mars rover is built with a Mars-appropriate battery). What transfers
    # between bodies in this study is the autonomy stack, not the hardware;
    # leaving one fixed battery would mean the Mars condition measured an
    # undersized vehicle rather than a decision-making strategy.
    battery_capacity: float | None = None
    fault_rate: float = 0.0  # expected faults per mission
    comm_delay: int = 0  # steps lost per intervention request
    replan_interval: int = 10  # forced replan cadence
    solar_rate: float = 2.0  # Wh harvested per step at full sun
    resume_charge_fraction: float = 0.6  # battery level that starts a new sortie
    prior_body: str = "moon"  # body the world-model prior came from
    max_slope_deg: float = 25.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MissionResult:
    config: dict
    seed: int
    termination: str
    success: bool
    science_return: float
    science_possible: float
    targets_visited: int
    targets_total: int
    energy_spent: float
    energy_generated: float
    final_charge: float
    min_charge: float
    steps: int
    distance_travelled: float
    interventions: int
    severe_slip_events: int
    mean_slip: float
    planner_replans: int
    nodes_expanded: int
    predicted_failure_prob: float
    hazard_refusals: int
    final_distance_from_home: float
    belief_snapshot: dict = field(default_factory=dict)
    history: list = field(default_factory=list)

    def to_row(self) -> dict:
        row = {
            k: v
            for k, v in self.__dict__.items()
            if k not in ("config", "history", "belief_snapshot")
        }
        row.update(self.config)
        row["seed"] = self.seed
        return row


def build_world_model(config: MissionConfig, prior: dict, adaptive: bool):
    cls = AdaptiveWorldModel if adaptive else WorldModel
    # Energy multipliers belong to the prior body, not the simulated body.
    # Using the target body's true values here would leak ground truth into an
    # OOD experiment. A lunar-prior robot sent to Mars must initially carry
    # lunar energy beliefs and update only through permitted observations.
    prior_params = TRUE_CLASS_PARAMS[config.prior_body]
    energy_multipliers = {
        int(klass): params.energy_multiplier for klass, params in prior_params.items()
    }
    return cls(
        size=config.size,
        class_prior=prior["means"],
        aleatoric_sd=prior["aleatoric_sd"],
        energy_multipliers=energy_multipliers,
    )


def _make_planner(name: str, config: MissionConfig, gravity: float):
    from .planners import make_planner

    return make_planner(name, max_slope_deg=config.max_slope_deg, gravity=gravity)


def run_mission(
    config: MissionConfig, seed: int, prior: dict | None = None, collect_history: bool = False
) -> MissionResult:
    from .autonomy.priors import default_prior

    rng = np.random.default_rng(seed)
    terrain = make_environment(
        config.body, seed=seed, size=config.size, max_slope_deg=config.max_slope_deg
    )

    # Inflate the true slip dispersion if the condition calls for a noisier
    # world. Applied to the terrain itself, so every planner faces it.
    if config.terrain_uncertainty != 1.0:
        scaled = {}
        for klass, params in terrain.class_params.items():
            scaled[klass] = type(params)(
                slip_mean=params.slip_mean,
                slip_dispersion=params.slip_dispersion * config.terrain_uncertainty,
                energy_multiplier=params.energy_multiplier,
                label=params.label,
            )
        terrain.class_params = scaled

    capacity = config.battery_capacity
    if capacity is None:
        from .robot.power import REFERENCE_GRAVITY

        capacity = BASE_BATTERY_CAPACITY * (terrain.gravity / REFERENCE_GRAVITY)

    mission = generate_mission(
        terrain,
        rng,
        n_targets=config.n_targets,
        risk_budget=config.risk_budget,
        max_steps=config.max_steps,
        energy_reserve=config.energy_reserve_fraction * capacity,
    )

    prior = prior or default_prior(config.prior_body)
    planner = _make_planner(config.planner, config, terrain.gravity)
    world_model = build_world_model(config, prior, adaptive=planner.adaptive)

    rover = Rover(
        row=mission.home[0],
        col=mission.home[1],
        max_slope_deg=config.max_slope_deg,
        power=PowerSystem(capacity=capacity, charge=capacity, solar_rate=config.solar_rate),
        sensors=SensorSuite(
            sensing_radius=config.sensing_radius,
            slope_noise_deg=1.2 * config.sensor_noise_scale,
            roughness_noise=0.05 * config.sensor_noise_scale,
            class_confusion=0.12 * config.sensor_noise_scale,
        ),
    )
    faults = FaultSchedule.draw(rng, config.max_steps, config.fault_rate)
    manager = MissionManager(mission, planner, world_model, terrain.gravity)
    manager.resume_charge_fraction = config.resume_charge_fraction

    path: list = []
    path_index = 0
    interventions = 0
    comm_wait = 0
    severe_slip_events = 0
    hazard_refusals = 0
    distance_travelled = 0.0
    min_charge = rover.power.charge
    predicted_failure_prob = 0.0
    slips: list[float] = []
    history: list[dict] = []
    termination = TERMINATION_TIMEOUT

    for step in range(1, config.max_steps + 1):
        rover.apply_faults(faults, step)

        if not rover.operational:
            termination = TERMINATION_IMMOBILIZED if rover.immobilized else TERMINATION_ENERGY
            break

        world_model.ingest_observations(rover.sense(terrain, rng))

        # Waiting on mission control after an intervention request.
        if comm_wait > 0:
            comm_wait -= 1
            rover.hold(float(terrain.illumination[rover.pos]))
            min_charge = min(min_charge, rover.power.charge)
            continue

        need_plan = (
            not path or path_index >= len(path) or step % max(config.replan_interval, 1) == 0
        )
        if need_plan:
            objective = manager.select_objective(
                rover.pos,
                rover.power.charge,
                charge_fraction=rover.power.fraction,
                solar_efficiency=rover.power.solar_efficiency,
                solar_rate=rover.power.solar_rate,
            )
            path = objective["path"] or []
            path_index = 1 if len(path) > 1 else 0
            predicted_failure_prob = objective.get("p_failure", predicted_failure_prob)

            if not path or len(path) < 2:
                if rover.pos == mission.home and not mission.remaining:
                    termination = TERMINATION_SUCCESS
                    break
                # No believable route: escalate to mission control. The delay
                # is the cost of not being able to solve it onboard.
                interventions += 1
                comm_wait = config.comm_delay
                # Ground relaxes the hazard threshold for one planning cycle.
                planner.hazard_threshold = min(0.95, planner.hazard_threshold + 0.15)
                rover.hold(float(terrain.illumination[rover.pos]))
                min_charge = min(min_charge, rover.power.charge)
                continue

        target_cell = path[path_index]
        dr = int(np.sign(target_cell[0] - rover.row))
        dc = int(np.sign(target_cell[1] - rover.col))
        outcome = rover.attempt_move(dr, dc, terrain, rng)

        if outcome["record"] is not None:
            planner.observe_slip(world_model, outcome["record"])
            slips.append(outcome["record"].slip)

        if outcome["moved"]:
            distance_travelled += float(np.hypot(dr, dc))
            path_index += 1
        else:
            reason = outcome["reason"]
            if reason == "slip_no_progress":
                severe_slip_events += 1
                # Being stuck is exactly when a fixed plan is worst: force a
                # replan so an adaptive model can act on what it just learned.
                path = []
            elif reason == "hazard_refused":
                hazard_refusals += 1
                world_model.hazard_prob[target_cell] = 1.0
                path = []
            elif reason == "insufficient_energy":
                termination = TERMINATION_ENERGY
                break
            elif reason == "off_map":
                path = []

        rover.power.recharge(float(terrain.illumination[rover.pos]))
        min_charge = min(min_charge, rover.power.charge)

        for science_target in mission.targets:
            if not science_target.visited and rover.pos == science_target.pos:
                science_target.visited = True
                manager.current_target = None
                path = []

        if rover.pos == mission.home and not mission.remaining and manager.returning:
            termination = TERMINATION_SUCCESS
            break

        if collect_history:
            history.append(
                {
                    "step": step,
                    "row": rover.row,
                    "col": rover.col,
                    "charge": rover.power.charge,
                    "science": mission.collected_value,
                    "slip": outcome["slip"],
                }
            )

        if not rover.operational:
            termination = TERMINATION_IMMOBILIZED if rover.immobilized else TERMINATION_ENERGY
            break

    at_home = rover.pos == mission.home
    objectives_resolved = not mission.remaining
    success = bool(
        rover.operational
        and at_home
        and objectives_resolved
        and termination in (TERMINATION_SUCCESS, TERMINATION_TIMEOUT)
    )
    if success:
        termination = TERMINATION_SUCCESS

    return MissionResult(
        config=config.to_dict(),
        seed=seed,
        termination=termination,
        success=success,
        science_return=mission.collected_value,
        science_possible=mission.total_value,
        targets_visited=sum(1 for t in mission.targets if t.visited),
        targets_total=len(mission.targets),
        energy_spent=rover.power.expended,
        energy_generated=rover.power.generated,
        final_charge=rover.power.charge,
        min_charge=min_charge,
        steps=step,
        distance_travelled=distance_travelled,
        interventions=interventions,
        severe_slip_events=severe_slip_events,
        mean_slip=float(np.mean(slips)) if slips else 0.0,
        planner_replans=planner.plan_calls,
        nodes_expanded=planner.nodes_expanded,
        predicted_failure_prob=float(predicted_failure_prob),
        hazard_refusals=hazard_refusals,
        final_distance_from_home=float(
            np.hypot(rover.row - mission.home[0], rover.col - mission.home[1])
        ),
        belief_snapshot=world_model.snapshot(),
        history=history,
    )

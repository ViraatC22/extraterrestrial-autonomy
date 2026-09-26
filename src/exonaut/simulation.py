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
    # Engine profile. "v1" is the engine the confirmatory study ran on and is
    # kept byte-for-byte so every committed result still reproduces. "v2"
    # switches on the fixes recorded in docs/RESEARCH_LOG.md (2026-09-25):
    # calibrated learner, faults inside the mission, independent random
    # streams, one-cycle intervention relaxation, and no livelock at the
    # lander. v2 is exploratory until a separately declared study uses it.
    engine: str = "v1"
    # v2 only: fault times are drawn within the first `fault_window` steps.
    # v1 drew them over the whole horizon, but missions end long before that,
    # so most scheduled faults never fired.
    fault_window: int = 50

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
    #: one record per planning decision, including every candidate's route
    decisions: list = field(default_factory=list)
    #: sparse per-frame snapshots of the whole-map belief (visualisation only)
    belief_frames: list = field(default_factory=list)
    #: home position and science-target layout, so a replay can be rendered
    #: without re-deriving the mission
    mission_layout: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        row = {
            k: v
            for k, v in self.__dict__.items()
            if k
            not in (
                "config",
                "history",
                "belief_snapshot",
                "mission_layout",
                "decisions",
                "belief_frames",
            )
        }
        row.update(self.config)
        row["seed"] = self.seed
        return row


def build_world_model(config: MissionConfig, prior: dict, adaptive: bool):
    cls = AdaptiveWorldModel if adaptive else WorldModel
    extra = {"calibrated_update": True} if (adaptive and config.engine == "v2") else {}
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
        **extra,
    )


def _make_planner(name: str, config: MissionConfig, gravity: float):
    from .planners import make_planner

    return make_planner(name, max_slope_deg=config.max_slope_deg, gravity=gravity)


def run_mission(
    config: MissionConfig,
    seed: int,
    prior: dict | None = None,
    collect_history: bool = False,
    collect_belief: bool = False,
    belief_stride: int = 3,
) -> MissionResult:
    from .autonomy.priors import default_prior

    if config.engine not in ("v1", "v2"):
        raise ValueError(f"unknown engine {config.engine!r}; expected 'v1' or 'v2'")
    v2 = config.engine == "v2"
    if v2:
        # Independent streams, so changing one factor (say, the fault rate)
        # leaves every other random draw exactly as it was.
        streams = np.random.SeedSequence(seed).spawn(4)
        mission_rng, fault_rng, sense_rng, slip_rng = (np.random.default_rng(s) for s in streams)
    else:
        # v1: one stream for everything, drawn in sequence (kept for
        # reproduction of the committed results).
        rng = np.random.default_rng(seed)
        mission_rng = fault_rng = sense_rng = slip_rng = rng
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
        mission_rng,
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
    fault_horizon = min(config.max_steps, config.fault_window) if v2 else config.max_steps
    faults = FaultSchedule.draw(fault_rng, fault_horizon, config.fault_rate)
    manager = MissionManager(mission, planner, world_model, terrain.gravity)
    manager.resume_charge_fraction = config.resume_charge_fraction
    base_hazard_threshold = planner.hazard_threshold

    path: list = []
    path_index = 0
    interventions = 0
    comm_wait = 0
    severe_slip_events = 0
    hazard_refusals = 0
    distance_travelled = 0.0
    min_charge = rover.power.charge
    predicted_failure_prob = 0.0
    objective_goal = None
    decision_reason = None
    last_candidates: list = []
    decisions: list[dict] = []
    decision_index = -1
    belief_frames: list[dict] = []
    slips: list[float] = []
    history: list[dict] = []
    termination = TERMINATION_TIMEOUT

    pending_faults: list[str] = []
    #: grid heading of the most recent completed move, degrees clockwise from
    #: grid north (towards row 0); None until the rover first moves
    heading_deg: float | None = None
    for step in range(1, config.max_steps + 1):
        fired = rover.apply_faults(faults, step)
        # Faults can fire on steps that record no frame (waiting on mission
        # control), so they are held until the next recorded frame.
        pending_faults.extend(str(event.fault_type) for event in fired)

        if not rover.operational:
            termination = TERMINATION_IMMOBILIZED if rover.immobilized else TERMINATION_ENERGY
            break

        world_model.ingest_observations(rover.sense(terrain, sense_rng))

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
            objective_goal = objective.get("goal")
            decision_reason = objective.get("reason")
            # Routes are kept once per decision rather than copied into every
            # frame; frames point at their decision by index.
            last_candidates = [
                {k: v for k, v in c.items() if k != "route"} for c in manager.last_candidates
            ]
            if collect_history:
                decisions.append(
                    {
                        "index": len(decisions),
                        "step": step,
                        "row": rover.row,
                        "col": rover.col,
                        "charge_fraction": rover.power.fraction,
                        "reason": decision_reason,
                        "risk_budget": mission.risk_budget,
                        "chosen_route": [tuple(c) for c in (objective["path"] or [])],
                        "candidates": [dict(c) for c in manager.last_candidates],
                    }
                )
                decision_index = len(decisions) - 1
            predicted_failure_prob = objective.get("p_failure", predicted_failure_prob)
            if v2 and planner.hazard_threshold != base_hazard_threshold:
                # The relaxation granted by ground applied to the planning
                # cycle just completed; restore the planner's own threshold.
                # (v1 never restored it, so it ratcheted up to 0.95.)
                planner.hazard_threshold = base_hazard_threshold

            if not path or len(path) < 2:
                if rover.pos == mission.home and not mission.remaining:
                    termination = TERMINATION_SUCCESS
                    break
                if v2 and rover.pos == mission.home and manager.returning:
                    # Home, but waiting for charge before another sortie. That
                    # is not "no believable route", so do not ask for help:
                    # recharge and reconsider. (v1 requested an intervention
                    # here on every step, a livelock that ended at the step
                    # limit in most of its timeouts.)
                    rover.hold(float(terrain.illumination[rover.pos]))
                    min_charge = min(min_charge, rover.power.charge)
                    continue
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
        outcome = rover.attempt_move(dr, dc, terrain, slip_rng)

        if outcome["record"] is not None:
            planner.observe_slip(world_model, outcome["record"])
            slips.append(outcome["record"].slip)

        if outcome["moved"]:
            distance_travelled += float(np.hypot(dr, dc))
            path_index += 1
            heading_deg = float(np.degrees(np.arctan2(dc, -dr)) % 360.0)
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
            # Enough per-step state to replay the mission and to show *why*
            # the robot did what it did: the route it was committed to, what
            # it currently believed about each terrain class, and whether it
            # had given up and turned for home.
            history.append(
                {
                    "step": step,
                    "row": rover.row,
                    "col": rover.col,
                    "charge": rover.power.charge,
                    "charge_fraction": rover.power.fraction,
                    "science": mission.collected_value,
                    "slip": outcome["slip"],
                    "moved": outcome["moved"],
                    "reason": outcome["reason"],
                    "planned_path": list(path[path_index:]) if path else [],
                    "goal": objective_goal,
                    "returning": manager.returning,
                    "targets_visited": sum(1 for t in mission.targets if t.visited),
                    "belief": {int(k): v["mean"] for k, v in world_model.snapshot().items()},
                    "belief_sd": {
                        int(k): v["epistemic_sd"] for k, v in world_model.snapshot().items()
                    },
                    "interventions": interventions,
                    "predicted_failure_prob": predicted_failure_prob,
                    "decision_reason": decision_reason,
                    "candidates": last_candidates,
                    "decision_index": decision_index,
                    "sensing_radius": rover.sensors.effective_radius(),
                    "energy_spent": rover.power.expended,
                    "faults": pending_faults,
                    "heading_deg": heading_deg,
                    "local_slope_deg": float(terrain.slope[rover.pos]),
                }
            )
            pending_faults = []
            if collect_belief and (len(history) - 1) % max(belief_stride, 1) == 0:
                from .autonomy import risk as _risk

                belief_frames.append(
                    {
                        "frame_index": len(history) - 1,
                        "step": step,
                        "observed": world_model.observed.copy(),
                        "believed_class": world_model.terrain_class.astype(np.int8).copy(),
                        "expected_slip": world_model.expected_slip_grid().astype(np.float32),
                        "slip_sd": world_model.total_slip_sd_grid().astype(np.float32),
                        "risk": _risk.cell_risk_grid(world_model).astype(np.float32),
                        "hazard_prob": world_model.hazard_prob.astype(np.float32).copy(),
                        "hazard_threshold": float(planner.hazard_threshold),
                        # the planner's own test (believed_traversable), whole map
                        "routable": world_model.believed_traversable_grid(
                            planner.max_slope_deg, planner.hazard_threshold
                        ),
                        "believed_slope": world_model.slope.astype(np.float32).copy(),
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
        decisions=decisions,
        belief_frames=belief_frames,
        mission_layout={
            "home": mission.home,
            "targets": [
                {
                    "id": t.target_id,
                    "row": t.row,
                    "col": t.col,
                    "value": t.value,
                    "visited": t.visited,
                    "abandoned": t.abandoned,
                }
                for t in mission.targets
            ],
        },
    )

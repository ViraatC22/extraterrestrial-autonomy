"""Single-rover agent state.

A Rover only knows what it has personally sensed plus whatever it has
received over the mesh network from other rovers it has been in comm range
with (see comms.py). This is what makes the communication-radius IV
meaningful: shrink it and rovers act on staler, more local information.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# 8-connected movement + stay in place.
ACTIONS = [
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
    (-1, -1),
    (-1, 1),
    (1, -1),
    (1, 1),
    (0, 0),
]
N_ACTIONS = len(ACTIONS)
STAY_ACTION = N_ACTIONS - 1

MOVE_COST = 1.0  # battery units per grid-cell moved (axial)
DIAGONAL_COST = math.sqrt(2.0)  # diagonal moves cover sqrt(2) cells of ground
IDLE_COST = 0.1  # battery units per step while stationary
SOLAR_RECHARGE = 0.6  # battery units per step when in sunlight
MAX_BATTERY = 100.0


def direction_to_action(dr: float, dc: float) -> int:
    """Map a desired (dr, dc) heading to the closest of the 8 discrete
    movement actions (by cosine similarity). Shared by every baseline
    policy so 'move toward this point' means the same thing everywhere."""
    if dr == 0 and dc == 0:
        return STAY_ACTION
    norm = (dr**2 + dc**2) ** 0.5
    best_action, best_score = STAY_ACTION, -np.inf
    for i, (adr, adc) in enumerate(ACTIONS[:-1]):
        anorm = (adr**2 + adc**2) ** 0.5
        score = (dr * adr + dc * adc) / (norm * anorm)
        if score > best_score:
            best_score = score
            best_action = i
    return best_action


def best_traversable_action(
    terrain, row: int, col: int, dr: float, dc: float, max_slope_deg: float
) -> int:
    """Like direction_to_action, but skips any of the 8 headings whose
    target cell isn't currently traversable, falling through to the
    next-closest-matching direction instead. Without this, a policy that
    always takes the single best-matching direction can get permanently
    wedged for the rest of the episode the moment that one heading happens
    to point at a hazard cell - a real rover's local obstacle avoidance
    would route around it, not freeze."""
    if dr == 0 and dc == 0:
        return STAY_ACTION
    norm = (dr**2 + dc**2) ** 0.5
    ranked = sorted(
        range(len(ACTIONS) - 1),
        key=lambda i: (
            -(dr * ACTIONS[i][0] + dc * ACTIONS[i][1])
            / (norm * (ACTIONS[i][0] ** 2 + ACTIONS[i][1] ** 2) ** 0.5)
        ),
    )
    for i in ranked:
        adr, adc = ACTIONS[i]
        if terrain.is_traversable(row + adr, col + adc, max_slope_deg):
            return i
    return STAY_ACTION


@dataclass
class Rover:
    rover_id: int
    row: int
    col: int
    sensor_radius: int = 4
    comm_radius: int = 12
    max_slope_deg: float = 25.0
    battery: float = MAX_BATTERY
    alive: bool = True
    # Cumulative battery units drawn for locomotion and idling over the whole
    # episode. Tracked separately from `battery` because solar recharge means
    # the final battery level does NOT reveal how much energy was expended.
    energy_spent: float = 0.0
    # known[(row, col)] = True if that cell has been confirmed explored,
    # either by this rover's own sensor or received from a peer.
    known: dict = field(default_factory=dict)
    path: list = field(default_factory=list)

    def __post_init__(self):
        self.path.append((self.row, self.col))

    @property
    def pos(self) -> tuple[int, int]:
        return (self.row, self.col)

    def sense(self, terrain) -> set[tuple[int, int]]:
        """Mark every cell within sensor_radius (line-of-sight distance,
        not blocked by terrain in this simplified model) as known."""
        newly_seen = set()
        size = terrain.size
        r0, r1 = max(0, self.row - self.sensor_radius), min(size, self.row + self.sensor_radius + 1)
        c0, c1 = max(0, self.col - self.sensor_radius), min(size, self.col + self.sensor_radius + 1)
        for r in range(r0, r1):
            for c in range(c0, c1):
                if (r - self.row) ** 2 + (c - self.col) ** 2 <= self.sensor_radius**2:
                    if (r, c) not in self.known:
                        newly_seen.add((r, c))
                    self.known[(r, c)] = True
        return newly_seen

    def receive(self, other_known: dict) -> None:
        """Merge another rover's known-cell map into this one (mesh relay)."""
        self.known.update(other_known)

    def try_move(self, action: int, terrain) -> bool:
        """Attempt to execute a movement action. Returns True if the rover
        actually moved (hazards / off-map / too-steep moves are rejected
        and treated as a stay, matching how a real rover's local hazard
        avoidance would refuse an unsafe command)."""
        if not self.alive:
            return False
        dr, dc = ACTIONS[action]
        if dr == 0 and dc == 0:
            self.battery = min(MAX_BATTERY, self.battery - IDLE_COST)
            self.energy_spent += IDLE_COST
            return False
        new_r, new_c = self.row + dr, self.col + dc
        if not terrain.is_traversable(new_r, new_c, self.max_slope_deg):
            self.battery = min(MAX_BATTERY, self.battery - IDLE_COST)
            self.energy_spent += IDLE_COST
            return False
        step_cost = MOVE_COST * (DIAGONAL_COST if dr != 0 and dc != 0 else 1.0)
        if self.battery < step_cost:
            return False
        self.row, self.col = new_r, new_c
        self.battery -= step_cost
        self.energy_spent += step_cost
        self.path.append((self.row, self.col))
        return True

    def apply_solar(self, in_shadow: bool) -> None:
        if not self.alive:
            return
        if not in_shadow:
            self.battery = min(MAX_BATTERY, self.battery + SOLAR_RECHARGE)
        if self.battery <= 0:
            self.alive = False

    def frontier_cells(self, terrain) -> list[tuple[int, int]]:
        """Cells this rover knows are traversable and adjacent to at least
        one unknown cell - the classic 'frontier' in frontier-based
        exploration."""
        frontiers = []
        for r, c in self.known:
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < terrain.size and 0 <= nc < terrain.size and (nr, nc) not in self.known:
                    frontiers.append((r, c))
                    break
        return frontiers

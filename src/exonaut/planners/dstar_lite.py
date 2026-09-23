"""D* Lite - incremental replanning.

Why this planner belongs in this study specifically: the project's question is
about revising decisions as new information arrives, and D* Lite is the
classical answer to that question. It repairs an existing search tree when
edge costs change instead of planning from scratch, which is what a rover
does when its sensors reveal that the route ahead is worse than believed.

It is therefore the control that separates two things this project could
otherwise confuse:

  * *replanning* - recomputing a route when the map changes (D* Lite does
    this efficiently; the A* planners do it by brute-force replanning), and
  * *model adaptation* - changing the beliefs that determine what the map
    says in the first place (only the adaptive planner does this).

A planner can replan constantly and still be wrong forever if its underlying
terrain model never updates. Including D* Lite makes that distinction
measurable rather than asserted.

Implementation follows Koenig and Likhachev's formulation: search proceeds
backwards from the goal, `rhs` is the one-step lookahead estimate of `g`, a
node is locally inconsistent when `g != rhs`, and the priority queue is keyed
by a pair with a travelling offset `k_m` that keeps old keys valid as the
robot moves.
"""

from __future__ import annotations

import heapq

import numpy as np

from .base import NEIGHBOURS, Planner
from .risk_aware import DEFAULT_WEIGHTS


class DStarLitePlanner(Planner):
    """Incremental replanner over the risk-aware cost surface.

    It shares `RiskAwarePlanner`'s objective so that a comparison against it
    isolates the search strategy rather than the cost function.
    """

    name = "dstar_lite"
    adaptive = False

    def __init__(self, weights: dict | None = None, **kwargs):
        super().__init__(**kwargs)
        self.weights = dict(DEFAULT_WEIGHTS if weights is None else weights)
        self._reset_search()

    def _reset_search(self) -> None:
        self.g: dict = {}
        self.rhs: dict = {}
        self.queue: list = []
        self.k_m = 0.0
        self.start = None
        self.goal = None
        self._entry_count = 0

    # -- cost surface (identical to the fixed risk-aware planner) ----------
    def step_cost(self, world_model, from_cell, to_cell, distance: float) -> float:
        from ..autonomy import risk

        w = self.weights
        row, col = to_cell
        energy = world_model.expected_energy(row, col, distance, self.gravity)
        cell_risk = risk.cell_risk(world_model, row, col)
        epistemic, _ = world_model.slip_uncertainty(row, col)
        return (
            w["distance"] * distance
            + w["energy"] * energy
            + w["risk"] * cell_risk
            + w["uncertainty"] * epistemic
        )

    def min_step_cost(self) -> float:
        return self.weights["distance"]

    # -- D* Lite core ------------------------------------------------------
    def _h(self, a, b) -> float:
        dr, dc = abs(a[0] - b[0]), abs(a[1] - b[1])
        octile = (dr + dc) + (np.sqrt(2.0) - 2.0) * min(dr, dc)
        return float(octile * self.min_step_cost())

    def _key(self, node) -> tuple[float, float]:
        value = min(self.g.get(node, np.inf), self.rhs.get(node, np.inf))
        return (value + self._h(self.start, node) + self.k_m, value)

    def _push(self, node) -> None:
        self._entry_count += 1
        heapq.heappush(self.queue, (*self._key(node), self._entry_count, node))

    def _neighbours(self, world_model, node):
        size = world_model.size
        for dr, dc in NEIGHBOURS:
            nb = (node[0] + dr, node[1] + dc)
            if not (0 <= nb[0] < size and 0 <= nb[1] < size):
                continue
            if nb != self.goal and not self.passable(world_model, *nb):
                continue
            yield nb, float(np.hypot(dr, dc))

    def _update_vertex(self, world_model, node) -> None:
        if node != self.goal:
            best = np.inf
            for nb, distance in self._neighbours(world_model, node):
                cost = self.step_cost(world_model, node, nb, distance)
                best = min(best, cost + self.g.get(nb, np.inf))
            self.rhs[node] = best
        if self.g.get(node, np.inf) != self.rhs.get(node, np.inf):
            self._push(node)

    def _compute_shortest_path(self, world_model, budget: int = 200_000) -> None:
        expansions = 0
        while self.queue and expansions < budget:
            top_key = self.queue[0][:2]
            start_key = self._key(self.start)
            start_inconsistent = self.g.get(self.start, np.inf) != self.rhs.get(self.start, np.inf)
            if top_key >= start_key and not start_inconsistent:
                break

            _, _, _, node = heapq.heappop(self.queue)
            expansions += 1
            self.nodes_expanded += 1

            g_value = self.g.get(node, np.inf)
            rhs_value = self.rhs.get(node, np.inf)
            if g_value == rhs_value:
                # Stale entry. The queue uses lazy deletion, so a node can be
                # queued while inconsistent and become consistent before it is
                # reached. Falling through to the raise branch here would set
                # g back to infinity and the node would oscillate forever
                # between "lower" and "raise" without the search progressing.
                continue

            new_key = self._key(node)
            if top_key < new_key:
                self._push(node)
            elif g_value > rhs_value:
                self.g[node] = self.rhs[node]
                for nb, _ in self._neighbours(world_model, node):
                    self._update_vertex(world_model, nb)
            else:
                self.g[node] = np.inf
                self._update_vertex(world_model, node)
                for nb, _ in self._neighbours(world_model, node):
                    self._update_vertex(world_model, nb)

    def plan(self, world_model, start, goal) -> list:
        self.plan_calls += 1
        if start == goal:
            return [start]
        size = world_model.size
        if not (0 <= goal[0] < size and 0 <= goal[1] < size):
            return []

        # The believed world changes between calls in ways this incremental
        # formulation does not receive as explicit edge-cost updates, so the
        # search is re-seeded whenever the goal changes. Within a goal the
        # tree is reused, which is where the incremental saving comes from.
        if self.goal != goal:
            self._reset_search()
            self.goal = goal
            # start must be set before the first key is computed: keys are
            # measured relative to the robot's current position.
            self.start = start
            self.rhs[goal] = 0.0
            self._push(goal)
        self.start = start

        self._compute_shortest_path(world_model)

        if self.g.get(start, np.inf) == np.inf and self.rhs.get(start, np.inf) == np.inf:
            return []

        # Walk greedily down the cost-to-go field.
        path = [start]
        current = start
        seen = {start}
        for _ in range(4 * size * size):
            if current == goal:
                return path
            best, best_cost = None, np.inf
            for nb, distance in self._neighbours(world_model, current):
                cost = self.step_cost(world_model, current, nb, distance) + self.g.get(nb, np.inf)
                if cost < best_cost and nb not in seen:
                    best, best_cost = nb, cost
            if best is None or not np.isfinite(best_cost):
                return path if len(path) > 1 else []
            path.append(best)
            seen.add(best)
            current = best
        return path if len(path) > 1 else []

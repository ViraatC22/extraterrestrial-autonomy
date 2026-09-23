"""Range-limited mesh networking between rovers.

Two rovers can exchange knowledge directly if they're within comm_radius of
each other; knowledge also relays transitively across a connected mesh
(rover A can reach rover C's data via B even if A and C are out of direct
range), mirroring the mesh-network behavior described for NASA's CADRE
rovers. Shrinking comm_radius is the main experimental lever for testing
how coordination degrades under realistic lunar comm constraints.
"""

from __future__ import annotations

import numpy as np


def connected_components(rovers, comm_radius: int) -> list[list[int]]:
    alive = [r for r in rovers if r.alive]
    n = len(alive)
    if n == 0:
        return []
    adjacency = np.zeros((n, n), dtype=bool)
    for i in range(n):
        for j in range(i + 1, n):
            dist = ((alive[i].row - alive[j].row) ** 2 + (alive[i].col - alive[j].col) ** 2) ** 0.5
            if dist <= comm_radius:
                adjacency[i, j] = adjacency[j, i] = True

    visited = [False] * n
    components = []
    for start in range(n):
        if visited[start]:
            continue
        stack, comp = [start], []
        visited[start] = True
        while stack:
            node = stack.pop()
            comp.append(alive[node].rover_id)
            for neighbor in range(n):
                if adjacency[node, neighbor] and not visited[neighbor]:
                    visited[neighbor] = True
                    stack.append(neighbor)
        components.append(comp)
    return components


def observable_teammates(env, rover) -> list:
    """The teammates whose position `rover` could legitimately know right now.

    A rover knows a teammate's location if it can either see it (within its
    own sensing radius) or reach it over the mesh network (same connected
    component, so the position can be relayed). Policies must use this
    rather than reading every rover's position out of the simulator: doing
    the latter makes a policy's coordination immune to the communication
    radius, which is precisely the variable under study.
    """
    others = [r for r in env.rovers if r.alive and r.rover_id != rover.rover_id]
    if not rover.alive or not others:
        return []

    reachable: set[int] = set()
    for component in connected_components(env.rovers, env.config.comm_radius):
        if rover.rover_id in component:
            reachable.update(component)
            break

    visible = []
    for other in others:
        dist = ((other.row - rover.row) ** 2 + (other.col - rover.col) ** 2) ** 0.5
        if other.rover_id in reachable or dist <= rover.sensor_radius:
            visible.append(other)
    return visible


def sync_mesh(rovers, comm_radius: int) -> None:
    """Merge the known-cell maps of every rover within the same connected
    mesh component, in place."""
    by_id = {r.rover_id: r for r in rovers}
    for component in connected_components(rovers, comm_radius):
        if len(component) < 2:
            continue
        merged: dict = {}
        for rid in component:
            merged.update(by_id[rid].known)
        for rid in component:
            by_id[rid].known.update(merged)

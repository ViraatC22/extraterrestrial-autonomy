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

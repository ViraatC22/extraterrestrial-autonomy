"""Matplotlib rendering of a SwarmEnv's current state, used by the
Streamlit live-simulation view."""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

ROVER_COLORS = ["#e63946", "#457b9d", "#2a9d8f", "#f4a261", "#8338ec", "#ffbe0b"]


def render_env(env, show_comm_links: bool = True, show_paths: bool = True):
    terrain = env.terrain
    fig, ax = plt.subplots(figsize=(6, 6))

    ax.imshow(terrain.elevation, cmap="gray", origin="upper", alpha=0.6)

    explored = np.ma.masked_where(~env.coverage, env.coverage.astype(float))
    ax.imshow(explored, cmap="spring", origin="upper", alpha=0.35, vmin=0, vmax=1)

    hazard_overlay = np.ma.masked_where(~terrain.hazard_mask, terrain.hazard_mask)
    ax.imshow(hazard_overlay, cmap="autumn", origin="upper", alpha=0.6)

    shadow_overlay = np.ma.masked_where(~terrain.shadow_mask, terrain.shadow_mask)
    ax.imshow(shadow_overlay, cmap="Blues", origin="upper", alpha=0.35)

    if show_comm_links:
        alive = [r for r in env.rovers if r.alive]
        for i in range(len(alive)):
            for j in range(i + 1, len(alive)):
                dist = ((alive[i].row - alive[j].row) ** 2 + (alive[i].col - alive[j].col) ** 2) ** 0.5
                if dist <= env.config.comm_radius:
                    ax.plot(
                        [alive[i].col, alive[j].col], [alive[i].row, alive[j].row],
                        color="lime", linewidth=0.8, alpha=0.6, zorder=2,
                    )

    for rover in env.rovers:
        color = ROVER_COLORS[rover.rover_id % len(ROVER_COLORS)]
        if show_paths and len(rover.path) > 1:
            path = np.array(rover.path)
            ax.plot(path[:, 1], path[:, 0], color=color, linewidth=1.0, alpha=0.5, zorder=1)
        marker = "o" if rover.alive else "x"
        ax.scatter([rover.col], [rover.row], c=color, s=90, marker=marker, edgecolors="black", zorder=3)

    coverage_frac = float(env.coverage[~terrain.hazard_mask].mean())
    alive_count = sum(1 for r in env.rovers if r.alive)
    ax.set_title(f"step {env.step_count} | coverage {coverage_frac * 100:.1f}% | alive {alive_count}/{len(env.rovers)}")
    ax.set_xlim(0, terrain.size)
    ax.set_ylim(terrain.size, 0)
    ax.set_xticks([])
    ax.set_yticks([])
    fig.tight_layout()
    return fig

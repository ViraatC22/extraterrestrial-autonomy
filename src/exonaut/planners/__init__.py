"""Planner registry.

Planners are addressed by short string names so a trial is fully described by
serializable data, which is what lets the experiment runner distribute work
across processes and record exactly what produced each row.
"""
from __future__ import annotations

from .astar import ShortestPathPlanner
from .base import Planner
from .risk_aware import RiskAwarePlanner

_REGISTRY = {
    ShortestPathPlanner.name: ShortestPathPlanner,
    RiskAwarePlanner.name: RiskAwarePlanner,
}


def register_planner(cls) -> None:
    _REGISTRY[cls.name] = cls


def available_planners() -> list[str]:
    return sorted(_REGISTRY)


def make_planner(name: str, **kwargs) -> Planner:
    if name not in _REGISTRY:
        raise ValueError(
            f"unknown planner {name!r}; available: {available_planners()}")
    return _REGISTRY[name](**kwargs)


__all__ = ["Planner", "RiskAwarePlanner", "ShortestPathPlanner",
           "available_planners", "make_planner", "register_planner"]

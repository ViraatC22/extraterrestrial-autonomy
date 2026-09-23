from .frontier import frontier_policy
from .potential_field import potential_field_policy
from .pheromone import PheromonePolicy

BASELINES = {
    "frontier": frontier_policy,
    "potential_field": potential_field_policy,
    "pheromone": PheromonePolicy,
}

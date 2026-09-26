"""The frontend's wire types must match the API's models field for field.

web/src/lib/types.ts mirrors src/exonaut/api/models.py by hand. If a field is
added, renamed or dropped on one side only, the interface would silently show
nothing (or a stale value) for it. This test parses the TypeScript interfaces
and compares their field names with the pydantic models'.
"""

import re
from pathlib import Path

import pytest

from exonaut.api import models

TYPES = (Path(__file__).resolve().parents[1] / "web/src/lib/types.ts").read_text()


def ts_fields(name: str) -> set[str]:
    match = re.search(rf"export interface {name}(?: extends (\w+))? \{{(.*?)\n\}}", TYPES, re.S)
    assert match, f"interface {name} not found in types.ts"
    parent, body = match.group(1), match.group(2)
    fields = set(re.findall(r"^\s{2}(\w+)\??:", body, re.M))
    return fields | (ts_fields(parent) if parent else set())


@pytest.mark.parametrize(
    "name",
    [
        "MissionRequest",
        "TerrainLayers",
        "CandidateEvaluation",
        "CandidateRoute",
        "TelemetryFrame",
        "Provenance",
        "Decision",
        "BeliefSnapshot",
        "MissionSummary",
        "PlannerInfo",
        "SplitInfo",
    ],
)
def test_typescript_interface_matches_pydantic_model(name):
    model = getattr(models, name)
    assert ts_fields(name) == set(model.model_fields), name

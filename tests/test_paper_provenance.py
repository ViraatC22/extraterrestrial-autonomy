"""Paper assets are generated, current, and traceable.

paper/PROVENANCE.yaml records, for every generated table, figure and macro the
paper uses, the script and inputs that produced it with their hashes. This
fails if a generated file was edited by hand, went stale against its inputs,
or the paper uses a result macro no generator defines.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _builder():
    spec = importlib.util.spec_from_file_location(
        "build_all_figures", ROOT / "scripts/build_all_figures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_paper_assets_match_their_recorded_provenance():
    builder = _builder()
    assert builder.PROVENANCE.exists(), "run python scripts/build_all_figures.py"
    assert builder.check() == []


def test_every_result_macro_in_the_paper_is_generated():
    assert _builder().undefined_paper_macros() == []

"""Test-wide settings.

API tests request held-out seeds on purpose; their accesses go to a temporary
log so they never appear in the project's record of held-out seed exposure.
"""

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolated_heldout_log(tmp_path_factory):
    import os

    path = tmp_path_factory.mktemp("logs") / "heldout_access_log.jsonl"
    previous = os.environ.get("EXONAUT_HELDOUT_LOG")
    os.environ["EXONAUT_HELDOUT_LOG"] = str(path)
    yield path
    if previous is None:
        os.environ.pop("EXONAUT_HELDOUT_LOG", None)
    else:
        os.environ["EXONAUT_HELDOUT_LOG"] = previous

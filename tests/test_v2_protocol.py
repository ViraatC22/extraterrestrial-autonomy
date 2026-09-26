"""The v2 seed manifest is fresh, disjoint, reproducible, and guarded.

These tests never build a confirmatory terrain: the guard refuses before any
generation happens, and refusals go to the test-only access log.
"""

import json

import pytest

from exonaut.experiments import v2_protocol as V2
from exonaut.experiments.protocol import load_quarantine, load_splits


@pytest.fixture(scope="module")
def manifest():
    m = V2.load_manifest()
    assert m is not None, "run scripts/freeze_v2_seed_manifest.py"
    return m


def test_manifest_rebuilds_exactly_from_its_recorded_algorithm(manifest):
    rebuilt = V2.build_manifest()
    assert rebuilt["splits"] == manifest["splits"]
    assert rebuilt["checksum"] == manifest["checksum"]
    assert manifest["master_seed"] == V2.MASTER_SEED


def test_v2_splits_are_pairwise_disjoint(manifest):
    splits = {k: set(v) for k, v in manifest["splits"].items()}
    names = list(splits)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            assert not (splits[a] & splits[b]), f"{a} and {b} overlap"
    assert len(manifest["splits"]["confirmatory_id"]) == len(splits["confirmatory_id"])


def test_v2_confirmatory_seeds_were_never_part_of_any_v1_split(manifest):
    v1 = load_splits()
    used_anywhere = set()
    for name in ("train", "validation", "test", "ood"):
        used_anywhere |= set(v1.get(name, exclude_quarantined=False))
    for burned in load_quarantine().values():
        used_anywhere |= set(burned)
    for name in V2.CONFIRMATORY:
        assert not (set(manifest["splits"][name]) & used_anywhere), name
    low, high = V2.CONFIRMATORY_RANGE
    assert all(low <= s < high for n in V2.CONFIRMATORY for s in manifest["splits"][n])


def test_development_splits_are_the_v1_development_splits(manifest):
    v1 = load_splits()
    assert manifest["splits"]["train"] == list(v1.get("train", exclude_quarantined=False))
    assert manifest["splits"]["validation"] == list(v1.get("validation", exclude_quarantined=False))


def test_building_a_confirmatory_terrain_is_refused_and_logged(manifest, _isolated_heldout_log):
    from exonaut.environments import make_environment

    seed = manifest["splits"]["confirmatory_ood"][0]
    before = (
        _isolated_heldout_log.read_text().splitlines() if _isolated_heldout_log.exists() else []
    )
    with pytest.raises(V2.ConfirmatorySeedAccessError):
        make_environment("mars", seed=seed, size=16)
    after = _isolated_heldout_log.read_text().splitlines()
    entry = json.loads(after[len(before)])
    assert entry == {**entry, "seed": seed, "split": "confirmatory_ood", "allowed": False}


def test_authorization_needs_the_frozen_plan_and_its_hash(monkeypatch, tmp_path):
    plan = tmp_path / "PREREGISTRATION_V2.md"
    monkeypatch.setattr(V2, "PREREGISTRATION_V2", plan)
    monkeypatch.setenv(V2.AUTH_ENV, "anything")
    assert not V2.authorized()  # no plan
    plan.write_text("frozen plan")
    assert not V2.authorized()  # wrong hash
    import hashlib

    monkeypatch.setenv(V2.AUTH_ENV, hashlib.sha256(b"frozen plan").hexdigest())
    assert V2.authorized()


def test_the_real_plan_does_not_exist_yet():
    """Study 2 is not frozen: nothing may be authorized in this repository state."""
    assert not V2.PREREGISTRATION_V2.exists()
    assert not V2.authorized()


def test_development_seeds_pass_the_guard():
    from exonaut.environments import make_environment

    make_environment("mars", seed=200_000, size=16)
    make_environment("moon", seed=100_100, size=16)


def test_calibration_and_power_scripts_accept_only_development_seeds():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("calibration_study", "power_analysis"):
        spec = importlib.util.spec_from_file_location(name, root / "scripts" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        check = module.check_development_seeds
        for split, seeds in module.SEED_USE.items():
            check(seeds, split)  # the seeds the script actually uses
            assert split in ("train", "validation")
        with pytest.raises(ValueError):
            check([300_010], "validation")  # a v1 test seed
        with pytest.raises(ValueError):
            check([V2.load_manifest()["splits"]["confirmatory_id"][0]], "validation")
        with pytest.raises(ValueError):
            check([200_000], "test")

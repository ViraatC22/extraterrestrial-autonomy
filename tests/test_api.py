"""Contract tests for the mission-control API.

The frontend is built against these shapes, so they are pinned here. The
tests also assert the property that makes the interface trustworthy: what the
API reports must equal what `run_mission` produced, not a recomputation.
"""

import pytest
from fastapi.testclient import TestClient

from exonaut.api import app

SMALL = {"size": 32, "n_targets": 2, "max_steps": 150}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def session(client):
    response = client.post("/start-mission", json={"seed": 200000, **SMALL})
    assert response.status_code == 200
    return response.json()


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_planners_include_the_experimental_arms(client):
    names = {p["name"] for p in client.get("/planners").json()}
    assert {"astar", "risk_aware_astar", "adaptive_risk_aware_astar"} <= names
    catalogue = {p["name"]: p for p in client.get("/planners").json()}
    assert catalogue["adaptive_risk_aware_astar"]["adaptive"] is True
    assert catalogue["risk_aware_astar"]["adaptive"] is False


def test_splits_expose_the_quarantine(client):
    splits = {s["name"]: s for s in client.get("/splits").json()}
    assert set(splits) == {"train", "validation", "test", "ood"}
    # burned seeds must be surfaced, and must not be the first usable seed
    assert splits["test"]["quarantined"], "quarantine not reported"
    assert splits["test"]["first"] not in splits["test"]["quarantined"]
    assert splits["ood"]["first"] not in splits["ood"]["quarantined"]


def test_terrain_layers_are_square_and_aligned(client):
    payload = client.get("/terrain", params={"body": "mars", "seed": 200000, "size": 32}).json()
    assert payload["size"] == 32
    for layer in ("elevation", "slope", "roughness", "illumination", "terrain_class", "hazard"):
        grid = payload[layer]
        assert len(grid) == 32, layer
        assert all(len(row) == 32 for row in grid), layer
    low, high = payload["elevation_range"]
    assert low < high


def test_terrain_rejects_unknown_body(client):
    assert client.get("/terrain", params={"body": "venus"}).status_code == 400


def test_start_mission_returns_a_consistent_summary(session):
    summary = session["summary"]
    assert summary["n_frames"] > 0
    assert summary["targets_total"] == SMALL["n_targets"]
    assert 0.0 <= summary["science_fraction"] <= 1.0
    assert summary["termination"] in {"success", "timeout", "immobilized", "energy_exhausted"}
    # science_fraction must be derived from the two reported quantities
    assert summary["science_fraction"] == pytest.approx(
        summary["science_return"] / summary["science_possible"]
    )


def test_mission_is_deterministic_for_the_same_request(client):
    first = client.post("/start-mission", json={"seed": 200001, **SMALL}).json()
    second = client.post("/start-mission", json={"seed": 200001, **SMALL}).json()
    assert first["session_id"] == second["session_id"]
    assert first["summary"] == second["summary"]


def test_api_summary_matches_the_engine_directly(client):
    """The API must report what run_mission produced, not a re-derivation."""
    from exonaut.simulation import MissionConfig, run_mission

    request = {"seed": 200002, "body": "mars", "planner": "risk_aware_astar", **SMALL}
    api = client.post("/start-mission", json=request).json()["summary"]

    config = MissionConfig(
        body="mars", planner="risk_aware_astar", size=32, n_targets=2, max_steps=150
    )
    direct = run_mission(config, seed=200002, collect_history=True)

    assert api["termination"] == direct.termination
    assert api["success"] == direct.success
    assert api["science_return"] == pytest.approx(direct.science_return)
    assert api["energy_spent"] == pytest.approx(direct.energy_spent)
    assert api["n_frames"] == len(direct.history)


def test_step_and_telemetry_agree(client, session):
    session_id = session["session_id"]
    frames = client.get(f"/missions/{session_id}/telemetry").json()
    assert len(frames) == session["summary"]["n_frames"]
    single = client.get(f"/missions/{session_id}/step", params={"index": 3}).json()
    assert single == frames[3]


def test_step_out_of_range_is_rejected(client, session):
    session_id = session["session_id"]
    total = session["summary"]["n_frames"]
    assert client.get(f"/missions/{session_id}/step", params={"index": total}).status_code == 416


def test_unknown_session_is_404(client):
    assert client.get("/missions/nope").status_code == 404
    assert client.get("/missions/nope/step").status_code == 404


def test_robot_state_defaults_to_the_last_frame(client, session):
    session_id = session["session_id"]
    state = client.get("/robot-state", params={"session_id": session_id}).json()
    frames = client.get(f"/missions/{session_id}/telemetry").json()
    assert state == frames[-1]


def test_adaptive_planner_beliefs_move_and_fixed_ones_do_not(client):
    """The frontend draws this distinction, so the API must actually carry it."""

    def belief_span(planner):
        started = client.post(
            "/start-mission",
            json={
                "seed": 200000,
                "body": "mars",
                "planner": planner,
                "size": 40,
                "n_targets": 3,
                "max_steps": 300,
            },
        ).json()
        frames = client.get(f"/missions/{started['session_id']}/telemetry").json()
        first, last = frames[0]["belief"], frames[-1]["belief"]
        return max(abs(last[k] - first[k]) for k in first)

    assert belief_span("risk_aware_astar") == pytest.approx(0.0, abs=1e-9)
    assert belief_span("adaptive_risk_aware_astar") > 0.01


def test_results_endpoint_serves_committed_experiment_data(client):
    available = client.get("/results/available").json()
    if "exonaut_main" not in available:
        pytest.skip("confirmatory results not present")
    payload = client.get("/results", params={"name": "exonaut_main"}).json()
    assert payload["n_missions"] > 0
    assert payload["descriptive"]
    assert payload["primary"]
    assert payload["metadata"].get("seed_split_checksum")


def test_websocket_streams_summary_then_frames(client, session):
    session_id = session["session_id"]
    with client.websocket_connect(f"/ws/telemetry/{session_id}") as socket:
        first = socket.receive_json()
        assert first["type"] == "summary"
        assert first["data"]["n_frames"] == session["summary"]["n_frames"]

        socket.send_json({"action": "speed", "interval": 0.005})
        frame = socket.receive_json()
        assert frame["type"] == "frame"
        assert frame["data"]["step"] >= 1
        socket.send_json({"action": "stop"})


def test_websocket_rejects_unknown_session(client):
    with client.websocket_connect("/ws/telemetry/does-not-exist") as socket:
        message = socket.receive_json()
        assert message["type"] == "error"


def test_reset_drops_sessions(client):
    started = client.post("/start-mission", json={"seed": 200003, **SMALL}).json()
    session_id = started["session_id"]
    assert client.get(f"/missions/{session_id}").status_code == 200
    assert client.delete(f"/missions/{session_id}").json()["dropped"] is True
    assert client.get(f"/missions/{session_id}").status_code == 404


def test_frames_carry_auditable_candidate_evaluations(client):
    """The Autonomy Inspector claims to show why a target was chosen, so the
    API has to carry the losing candidates and their rejection reasons too."""
    started = client.post(
        "/start-mission",
        json={
            "seed": 200000,
            "body": "mars",
            "planner": "adaptive_risk_aware_astar",
            "size": 44,
            "n_targets": 4,
            "max_steps": 300,
        },
    ).json()
    frames = client.get(f"/missions/{started['session_id']}/telemetry").json()

    scored = [f for f in frames if f["candidates"]]
    assert scored, "no decision points recorded"

    frame = scored[0]
    assert len(frame["candidates"]) >= 2, "cannot audit a choice with one option"

    selected = [c for c in frame["candidates"] if c["selected"]]
    assert len(selected) <= 1, "more than one candidate marked selected"

    for candidate in frame["candidates"]:
        if not candidate["reachable"]:
            assert candidate["rejected"], "unreachable candidate lacks a reason"
            continue
        assert candidate["expected_energy"] is not None
        assert 0.0 <= candidate["p_failure"] <= 1.0
        assert candidate["utility"] is not None

    # the selected candidate must be the highest-utility one that was not rejected
    eligible = [c for c in frame["candidates"] if c["reachable"] and c["rejected"] is None]
    if selected and eligible:
        best = max(eligible, key=lambda c: c["utility"])
        assert best["target_id"] == selected[0]["target_id"], (
            "selected candidate is not the highest-utility eligible one"
        )


def _start(client, seed=200000, **extra):
    body = {
        "seed": seed,
        "body": "mars",
        "planner": "adaptive_risk_aware_astar",
        "size": 40,
        "n_targets": 3,
        "max_steps": 250,
        **extra,
    }
    return client.post("/start-mission", json=body).json()


def test_provenance_identifies_the_run_and_its_seed_split(client):
    started = _start(client, seed=200000)
    prov = started["summary"]["provenance"]
    assert prov["seed_split"] == "validation"
    assert prov["seed_quarantined"] is False
    assert prov["planner_adaptive"] is True
    assert len(prov["config_digest"]) == 12
    assert prov["config"]["body"] == "mars"


def test_held_out_and_quarantined_seeds_are_flagged(client):
    test_seed = _start(client, seed=300010)["summary"]["provenance"]
    assert test_seed["seed_split"] == "test"
    burned = _start(client, seed=300000)["summary"]["provenance"]
    assert burned["seed_split"] == "test" and burned["seed_quarantined"] is True


def test_decisions_carry_a_route_for_every_reachable_candidate(client):
    started = _start(client)
    decisions = client.get(f"/missions/{started['session_id']}/decisions").json()
    assert decisions and len(decisions) == started["summary"]["n_decisions"]
    for decision in decisions:
        for cand in decision["candidates"]:
            if cand["reachable"]:
                route = cand["route"]
                assert route[0] == [decision["row"], decision["col"]], "route must start at rover"
                assert route[-1] == [cand["row"], cand["col"]], "route must end at target"


def test_belief_snapshot_separates_belief_from_truth(client):
    started = _start(client)
    sid, n = started["session_id"], started["summary"]["n_frames"]
    early = client.get(f"/missions/{sid}/belief", params={"index": 0}).json()
    late = client.get(f"/missions/{sid}/belief", params={"index": n - 1}).json()
    assert early["frame_index"] <= 0 + 0 or early["frame_index"] == 0
    assert late["frame_index"] <= n - 1
    # the rover learns about more of the map over time
    seen_early = sum(map(sum, early["observed"]))
    seen_late = sum(map(sum, late["observed"]))
    assert seen_late >= seen_early > 0
    # truth is identical across frames; belief is not
    assert early["true_slip"] == late["true_slip"]
    size = started["summary"]["provenance"]["config"]["size"]
    assert len(late["risk"]) == size and all(0 <= v <= 1 for row in late["risk"] for v in row)


def test_failure_case_studies_reproduce_their_committed_rows(client):
    """Every case study shown is a re-run; it must match the committed result."""
    body = client.get("/failures", params={"condition": "mars_ood"}).json()
    assert body["n_missions"] > 0
    seen = 0
    for cat in body["categories"]:
        assert 0 <= cat["share"] <= 1
        rep = cat["representative"]
        if rep is None:
            continue
        seen += 1
        assert rep["reproduces_committed_row"] is True, cat["key"]
        summary = client.get(f"/missions/{rep['session_id']}").json()
        assert summary["seed"] == rep["seed"]
        assert summary["provenance"]["seed_split"] == "ood"
    assert seen >= 2


def test_sweep_points_use_validation_seeds_only(client):
    body = client.get(
        "/sweep-point",
        params={"variable": "fault_rate", "value": 1.0, "planner": "astar", "n_seeds": 3},
    ).json()
    assert body["n"] == 3
    assert all(200000 <= s < 300000 for s in body["seeds"]), "sweep touched non-validation seeds"
    s = body["success"]
    assert 0 <= s["low"] <= s["mean"] <= s["high"] <= 1
    assert body["config"]["fault_rate"] == 1.0


def test_sweep_rejects_unknown_or_out_of_range_variables(client):
    assert client.get("/sweep-point", params={"variable": "seed", "value": 1}).status_code == 400
    assert (
        client.get("/sweep-point", params={"variable": "risk_budget", "value": 7}).status_code
        == 400
    )

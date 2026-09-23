"""FastAPI service exposing the EXONAUT engine to the mission-control UI.

The frontend is a *client* of the research engine. Every value it displays is
produced here by the same code the experiments run, so the interface cannot
show a number the science did not produce.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ..experiments.protocol import load_quarantine, load_splits
from .models import (
    MissionRequest,
    MissionStarted,
    MissionSummary,
    PlannerInfo,
    SplitInfo,
    TelemetryFrame,
    TerrainLayers,
)
from .service import MissionStore, frame_payload, planner_catalogue, summarize, terrain_payload

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = PROJECT_ROOT / "data" / "results"

app = FastAPI(
    title="EXONAUT mission control",
    version="0.2.0",
    description=(
        "Read-only window onto the EXONAUT research engine. Missions are run by "
        "the same code path as the experiments and replayed frame by frame."
    ),
)

# The UI runs on a different port in development. Allowed origins are explicit
# rather than "*" so the service does not quietly become callable from anywhere
# if it is ever exposed beyond localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

store = MissionStore()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "exonaut", "version": app.version}


@app.get("/planners", response_model=list[PlannerInfo])
def planners() -> list[PlannerInfo]:
    return planner_catalogue()


@app.get("/splits", response_model=list[SplitInfo])
def splits() -> list[SplitInfo]:
    """Seed splits, with the quarantine surfaced rather than hidden.

    The UI shows which seeds are spent so a user browsing interactively knows
    when they are looking at held-out data.
    """
    frozen = load_splits()
    quarantine = load_quarantine()
    out = []
    for name in ("train", "validation", "test", "ood"):
        seeds = frozen.get(name)
        out.append(
            SplitInfo(
                name=name,
                size=len(seeds),
                first=seeds[0],
                last=seeds[-1],
                quarantined=sorted(quarantine.get(name, [])),
            )
        )
    return out


@app.get("/terrain", response_model=TerrainLayers)
def terrain(
    body: str = Query("mars"),
    seed: int = Query(200000),
    size: int = Query(56, ge=16, le=128),
) -> TerrainLayers:
    if body not in ("moon", "mars"):
        raise HTTPException(400, f"unknown body {body!r}")
    return terrain_payload(body, seed, size)


@app.post("/start-mission", response_model=MissionStarted)
def start_mission(request: MissionRequest) -> MissionStarted:
    try:
        session_id, session = store.run(request)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return MissionStarted(session_id=session_id, summary=summarize(session_id, session))


@app.get("/missions/{session_id}", response_model=MissionSummary)
def mission_summary(session_id: str) -> MissionSummary:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "unknown session")
    return summarize(session_id, session)


@app.get("/missions/{session_id}/step", response_model=TelemetryFrame)
def mission_step(session_id: str, index: int = Query(0, ge=0)) -> TelemetryFrame:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "unknown session")
    history = session["result"].history
    if not history:
        raise HTTPException(404, "mission produced no frames")
    if index >= len(history):
        raise HTTPException(416, f"step {index} out of range (0..{len(history) - 1})")
    return frame_payload(history[index])


@app.get("/missions/{session_id}/telemetry", response_model=list[TelemetryFrame])
def mission_telemetry(
    session_id: str,
    start: int = Query(0, ge=0),
    limit: int = Query(2000, ge=1, le=5000),
) -> list[TelemetryFrame]:
    """Whole recorded history, for clients that would rather scrub than stream."""
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "unknown session")
    history = session["result"].history[start : start + limit]
    return [frame_payload(frame) for frame in history]


@app.get("/robot-state", response_model=TelemetryFrame)
def robot_state(session_id: str, index: int = Query(-1)) -> TelemetryFrame:
    """Latest known robot state, or a specific step. `index=-1` means the end."""
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "unknown session")
    history = session["result"].history
    if not history:
        raise HTTPException(404, "mission produced no frames")
    return frame_payload(history[index if index >= 0 else -1])


@app.delete("/missions/{session_id}")
def reset_mission(session_id: str) -> dict:
    return {"dropped": store.drop(session_id)}


@app.post("/reset")
def reset_all() -> dict:
    return {"dropped": store.clear()}


@app.get("/results")
def results(name: str = Query("exonaut_main")) -> dict:
    """Committed experiment results plus their provenance.

    Served from the same files the paper is generated from, so the interface
    and the paper cannot disagree.
    """
    from ..experiments.analysis import descriptive_table, generalization_gap, primary_analysis
    from ..experiments.io import load_results

    try:
        frame = load_results(name, results_dir=RESULTS_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    metadata_path = RESULTS_DIR / f"{name}.metadata.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}

    primary = primary_analysis(frame)
    return {
        "name": name,
        "n_missions": int(len(frame)),
        "metadata": metadata,
        "descriptive": descriptive_table(frame).to_dict(orient="records"),
        "primary": primary.to_dict(orient="records") if not primary.empty else [],
        "generalization_gap": generalization_gap(frame).to_dict(orient="records"),
    }


@app.get("/results/available")
def available_results() -> list[str]:
    stems = set()
    for pattern in ("*.parquet", "*.csv"):
        for path in RESULTS_DIR.glob(pattern):
            if path.stem.endswith(("_primary", "_secondary")):
                continue
            stems.add(path.stem)
    return sorted(stems)


@app.websocket("/ws/telemetry/{session_id}")
async def telemetry_socket(websocket: WebSocket, session_id: str) -> None:
    """Stream a mission's frames as if they were arriving live.

    The mission has already been computed; this paces the recorded frames so
    the interface can show the robot moving. Pacing is a presentation choice
    and changes nothing about the underlying result.
    """
    await websocket.accept()
    session = store.get(session_id)
    if session is None:
        await websocket.send_json({"type": "error", "message": "unknown session"})
        await websocket.close()
        return

    history = session["result"].history
    summary = summarize(session_id, session)
    await websocket.send_json({"type": "summary", "data": summary.model_dump(mode="json")})

    interval = 0.08
    index = 0
    playing = True
    try:
        while index < len(history):
            # Non-blocking check for client control messages.
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=0.001)
            except TimeoutError:
                message = None
            except (WebSocketDisconnect, RuntimeError):
                return

            if message:
                action = message.get("action")
                if action == "pause":
                    playing = False
                elif action == "play":
                    playing = True
                elif action == "speed":
                    interval = max(0.005, min(1.0, float(message.get("interval", interval))))
                elif action == "seek":
                    index = max(0, min(len(history) - 1, int(message.get("index", index))))
                elif action == "stop":
                    break

            if not playing:
                await asyncio.sleep(0.05)
                continue

            await websocket.send_json(
                {"type": "frame", "data": frame_payload(history[index]).model_dump(mode="json")}
            )
            index += 1
            await asyncio.sleep(interval)

        await websocket.send_json({"type": "complete", "termination": summary.termination})
    except WebSocketDisconnect:
        return
    finally:
        with contextlib.suppress(RuntimeError):
            await websocket.close()

"""Live data path (coordinator).

    camera ──WS /camera/ws (JPEG per message) or POST /video/frames──► video cache + model worker
    model worker ◄──WS /model/ws──► coordinator (routes/model.py)
    debug only: simulator labels / risk_pipeline --mode prod frame records ──POST /telemetry──► score
    phone, dashboard ◄──WS /ws── trip_started, state, emergency, section, trip_ended
"""

import logging

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status

from app.coordinator.deps import CoordinatorDep, Hub, TripRepo
from app.coordinator.services import trips as trip_service
from app.coordinator.services.coordinator import DebugFeedRefused
from app.coordinator.services.video import is_jpeg
from app.domain.enums import LiveEvent
from app.schemas.trip import TelemetryTick, TripState

router = APIRouter(tags=["live (coordinator)"])
logger = logging.getLogger(__name__)

MAX_FRAME_BYTES = 2_000_000
# The car has one cabin camera (on the rear-view mirror). A second stream would interleave two people's frames
# into one model, which then sees "two drivers" (rivian_model, 7. 11.). The first camera keeps the slot.
ONE_CAMERA = "Another camera is already streaming: the coordinator takes one cabin camera"
NO_ACTIVE_TRIP = "No active trip - start one from the app first"
MODEL_WORKER_DRIVES = (
    "A model worker is connected and drives the score: frame records on /telemetry are a debug feed "
    "(risk_pipeline.py --mode prod). Stop the worker to use it."
)


@router.post("/telemetry")
async def ingest_telemetry(tick: TelemetryTick, repo: TripRepo, coordinator: CoordinatorDep) -> TripState:
    """Debug feed: labels (simulator) and/or a model frame record (~2/s) from a model that scored it by itself.

    The real path doesn't use this: camera -> coordinator -> model worker (WS /model/ws), and the coordinator
    computes the risk. While a worker is connected, frame records are refused (409) so both never score one trip.
    """
    trip = repo.active()
    if trip is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_ACTIVE_TRIP)
    try:
        return await coordinator.on_telemetry(trip, tick)
    except DebugFeedRefused:
        raise HTTPException(status.HTTP_409_CONFLICT, MODEL_WORKER_DRIVES) from None


@router.post(
    "/video/frames",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def ingest_video_frame(request: Request, coordinator: CoordinatorDep) -> Response:
    """One camera JPEG as the raw body (`Content-Type: image/jpeg`). WS /camera/ws is the faster way.

    Frames go to the video cache (5 min) and to the model worker, if one is connected.
    """
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "image/jpeg":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Send one JPEG frame as image/jpeg")
    if int(request.headers.get("content-length") or 0) > MAX_FRAME_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Frame larger than {MAX_FRAME_BYTES} bytes")
    data = await request.body()
    if len(data) > MAX_FRAME_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Frame larger than {MAX_FRAME_BYTES} bytes")
    if not is_jpeg(data):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Body is not a JPEG image")
    if not coordinator.on_video_frame(data):
        raise HTTPException(status.HTTP_409_CONFLICT, NO_ACTIVE_TRIP)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.websocket("/camera/ws")
async def camera_stream(websocket: WebSocket, coordinator: CoordinatorDep) -> None:
    """The camera's stream: one binary message per JPEG frame (`tools/camera_stream.py`).

    Frames are dropped while no trip is active; the socket stays open. Text messages are ignored.
    Only one camera at a time: while one streams, a second connection is refused (policy violation, 1008);
    tools/camera_stream.py keeps retrying and takes over once the first one disconnects.
    """
    if coordinator.camera_clients >= 1:
        logger.warning("Second camera refused on /camera/ws: one is already streaming")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=ONE_CAMERA)
        return
    coordinator.camera_connected(+1)  # before the first await, so two simultaneous connections can't both pass
    try:
        await websocket.accept()
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            data = message.get("bytes")
            if data and len(data) <= MAX_FRAME_BYTES and is_jpeg(data):
                coordinator.on_video_frame(data)
    except WebSocketDisconnect:
        pass
    finally:
        coordinator.camera_connected(-1)


@router.websocket("/ws")
async def live_updates(websocket: WebSocket, repo: TripRepo, hub: Hub) -> None:
    """The phone and the dashboard keep this open. Every message is {"type": LiveEvent, "data": ...}."""
    await hub.connect(websocket)
    try:
        if (trip := repo.active()) is not None:
            await hub.send(websocket, LiveEvent.STATE, trip_service.to_state(trip))
        while True:
            await websocket.receive_text()  # nothing expected from the app; keeps the socket open
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket)

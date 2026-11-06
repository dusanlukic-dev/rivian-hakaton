"""Live data path: camera models -> POST /telemetry (+ /video/frames) -> backend -> WS /ws -> mobile app."""

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status

from app.api.deps import Hub, Recorder, Speed, TripRepo
from app.domain.enums import LiveEvent
from app.schemas.trip import TelemetryTick, TripState
from app.services import trips as trip_service
from app.services.video import is_jpeg

router = APIRouter(tags=["live"])

MAX_FRAME_BYTES = 2_000_000
NO_ACTIVE_TRIP = "No active trip - start one from the app first"


@router.post("/telemetry")
async def ingest_telemetry(
    tick: TelemetryTick, repo: TripRepo, hub: Hub, speed: Speed, recorder: Recorder
) -> TripState:
    """Called by the camera models (~2x per second). Applies to the trip in progress."""
    trip = repo.active()
    if trip is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_ACTIVE_TRIP)

    reading = speed.resolve(trip.id, tick.timestamp, tick.speed_kmh)
    emergency = trip_service.process_tick(trip, tick, reading.speed_kmh, reading.source)
    recorder.on_tick(trip, tick.timestamp, reading)
    state = trip_service.to_state(trip)
    await hub.broadcast(LiveEvent.STATE, state)
    if emergency:
        await hub.broadcast(LiveEvent.EMERGENCY, state)
    return state


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
async def ingest_video_frame(request: Request, repo: TripRepo, recorder: Recorder) -> Response:
    """Called by the camera side (~8 fps): one JPEG frame as the raw body (`Content-Type: image/jpeg`).

    The backend keeps only the last few seconds in memory and stores a clip around each risky moment.
    """
    if repo.active() is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_ACTIVE_TRIP)
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "image/jpeg":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Send one JPEG frame as image/jpeg")
    if int(request.headers.get("content-length") or 0) > MAX_FRAME_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Frame larger than {MAX_FRAME_BYTES} bytes")
    data = await request.body()
    if len(data) > MAX_FRAME_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Frame larger than {MAX_FRAME_BYTES} bytes")
    if not is_jpeg(data):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Body is not a JPEG image")
    recorder.on_video_frame(data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.websocket("/ws")
async def live_updates(websocket: WebSocket, repo: TripRepo, hub: Hub) -> None:
    """The mobile app keeps this open. Every message is {"type": LiveEvent, "data": ...}."""
    await hub.connect(websocket)
    try:
        if (trip := repo.active()) is not None:
            await hub.send(websocket, LiveEvent.STATE, trip_service.to_state(trip))
        while True:
            await websocket.receive_text()  # nothing expected from the app yet; keeps the socket open
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket)

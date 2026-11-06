"""Live data path: camera models -> POST /telemetry -> backend -> WS /ws -> mobile app."""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status

from app.api.deps import Hub, TripRepo
from app.domain.enums import LiveEvent
from app.schemas.trip import TelemetryTick, TripState
from app.services import trips as trip_service

router = APIRouter(tags=["live"])


@router.post("/telemetry")
async def ingest_telemetry(tick: TelemetryTick, repo: TripRepo, hub: Hub) -> TripState:
    """Called by the camera models (~1x per second). Applies to the trip in progress."""
    trip = repo.active()
    if trip is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No active trip - start one from the app first")

    emergency = trip_service.process_tick(trip, tick)
    state = trip_service.to_state(trip)
    await hub.broadcast(LiveEvent.STATE, state)
    if emergency:
        await hub.broadcast(LiveEvent.EMERGENCY, state)
    return state


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

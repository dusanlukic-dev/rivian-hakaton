from fastapi import APIRouter, HTTPException, status

from app.api.deps import Hub, OptionalUser, Recorder, Speed, TripDep, TripRepo, VisibleTripDep
from app.domain.enums import LiveEvent
from app.schemas.trip import TripCreate, TripState, TripSummary
from app.services import history
from app.services import trips as trip_service

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_trip(
    body: TripCreate, repo: TripRepo, hub: Hub, speed: Speed, recorder: Recorder, user: OptionalUser
) -> TripState:
    """Called by the app when the drive starts. Ends any trip still in progress.

    Logged in (Bearer token): the trip belongs to the account. Without login, `driver_id` is required.
    """
    try:
        trip, previous = trip_service.start_trip(repo, body, user)
    except trip_service.MissingDriver:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "driver_id is required when starting a trip without logging in"
        ) from None
    if previous is not None:
        recorder.trip_ended(previous)
        speed.end_trip(previous.id)
        await hub.broadcast(LiveEvent.TRIP_ENDED, trip_service.to_summary(previous))
    recorder.trip_started(trip, speed_scenario=speed.scenario_for(trip.id).name)
    state = trip_service.to_state(trip)
    await hub.broadcast(LiveEvent.TRIP_STARTED, state)
    return state


@router.get("")
async def list_trips(
    repo: TripRepo, recorder: Recorder, user: OptionalUser, driver_id: str | None = None
) -> list[TripSummary]:
    """History, oldest first, from Postgres (survives restarts). Logged in: your trips (`driver_id` is
    ignored). Not logged in: trips started without login, optionally only one `driver_id`'s."""
    return await history.list_trips(repo, recorder, user, driver_id)


@router.get("/{trip_id}")
def get_trip_state(trip: VisibleTripDep) -> TripState:
    return trip_service.to_state(trip)


@router.post("/{trip_id}/end")
async def end_trip(trip: TripDep, hub: Hub, speed: Speed, recorder: Recorder) -> TripSummary:
    """Open to the car itself (the dashboard can end a trip without the driver's token)."""
    ended_now = trip_service.end_trip(trip)
    summary = trip_service.to_summary(trip)
    if ended_now:
        recorder.trip_ended(trip)
        speed.end_trip(trip.id)
        await hub.broadcast(LiveEvent.TRIP_ENDED, summary)
    return summary


@router.get("/{trip_id}/summary")
async def get_trip_summary(trip_id: str, repo: TripRepo, recorder: Recorder, user: OptionalUser) -> TripSummary:
    """Works for the active trip and, from Postgres, for any earlier one (also after a restart)."""
    try:
        return await history.summary(trip_id, repo, recorder, user)
    except history.TripNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Trip {trip_id} not found") from None

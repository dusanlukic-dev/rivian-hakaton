from fastapi import APIRouter, status

from app.api.deps import Hub, TripDep, TripRepo
from app.domain.enums import LiveEvent
from app.schemas.trip import TripCreate, TripState, TripSummary
from app.services import trips as trip_service

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_trip(body: TripCreate, repo: TripRepo, hub: Hub) -> TripState:
    """Called by the app when the drive starts. Ends any trip still in progress."""
    trip, previous = trip_service.start_trip(repo, body)
    if previous is not None:
        await hub.broadcast(LiveEvent.TRIP_ENDED, trip_service.to_summary(previous))
    state = trip_service.to_state(trip)
    await hub.broadcast(LiveEvent.TRIP_STARTED, state)
    return state


@router.get("")
def list_trips(repo: TripRepo, driver_id: str | None = None) -> list[TripSummary]:
    return [trip_service.to_summary(t) for t in repo.list(driver_id)]


@router.get("/{trip_id}")
def get_trip_state(trip: TripDep) -> TripState:
    return trip_service.to_state(trip)


@router.post("/{trip_id}/end")
async def end_trip(trip: TripDep, hub: Hub) -> TripSummary:
    ended_now = trip_service.end_trip(trip)
    summary = trip_service.to_summary(trip)
    if ended_now:
        await hub.broadcast(LiveEvent.TRIP_ENDED, summary)
    return summary


@router.get("/{trip_id}/summary")
def get_trip_summary(trip: TripDep) -> TripSummary:
    return trip_service.to_summary(trip)

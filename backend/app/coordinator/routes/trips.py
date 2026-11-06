"""Live trips (coordinator): start, end, current state. History and reports are the server's (/trips GET...)."""

from fastapi import APIRouter, HTTPException, status

from app.coordinator.deps import CoordinatorDep, OptionalUser, TripDep, VisibleTripDep
from app.coordinator.services import trips as trip_service
from app.schemas.trip import TripCreate, TripState, TripSummary

router = APIRouter(prefix="/trips", tags=["trips (coordinator)"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_trip(body: TripCreate, coordinator: CoordinatorDep, user: OptionalUser) -> TripState:
    """Called by the app when the drive starts. Ends any trip still in progress.

    Logged in (Bearer token): the trip belongs to the account. Without login, `driver_id` is required.
    """
    try:
        return await coordinator.start_trip(body, user)
    except trip_service.MissingDriver:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "driver_id is required when starting a trip without logging in"
        ) from None


@router.get("/{trip_id}")
def get_trip_state(trip: VisibleTripDep) -> TripState:
    """The live state of a trip this coordinator is driving (or drove since it started)."""
    return trip_service.to_state(trip)


@router.post("/{trip_id}/end")
async def end_trip(trip: TripDep, coordinator: CoordinatorDep) -> TripSummary:
    """Open to the car itself (the dashboard can end a trip without the driver's token).

    Waits (up to 3 s) until the server has the whole trip, so the report opened right after is complete.
    """
    return await coordinator.end_trip(trip)

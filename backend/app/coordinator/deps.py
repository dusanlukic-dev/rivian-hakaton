from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.coordinator.repositories.trips import InMemoryTripRepository, get_trip_repository
from app.coordinator.services.coordinator import Coordinator, get_coordinator
from app.coordinator.services.live import LiveHub, get_live_hub
from app.coordinator.services.server_client import ServerRejected, ServerUnavailable
from app.coordinator.services.speed import SpeedService, get_speed_service
from app.domain.access import can_see
from app.domain.trip import Trip
from app.schemas.auth import User

CoordinatorDep = Annotated[Coordinator, Depends(get_coordinator)]
TripRepo = Annotated[InMemoryTripRepository, Depends(get_trip_repository)]
Hub = Annotated[LiveHub, Depends(get_live_hub)]
Speed = Annotated[SpeedService, Depends(get_speed_service)]

bearer = HTTPBearer(auto_error=False, description="Token from POST /auth/login or /auth/register")
BearerToken = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]

_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


async def get_optional_user(coordinator: CoordinatorDep, credentials: BearerToken) -> User | None:
    """Who is driving. Accounts live on the server, so the coordinator asks it (GET /auth/me, cached 30 s)."""
    if credentials is None:
        return None
    if coordinator.server is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The coordinator is still starting")
    try:
        user = await coordinator.server.user_for_token(credentials.credentials)
    except (ServerUnavailable, ServerRejected) as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Can't check the login: the server is unreachable ({e})"
        ) from e
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token - log in again", _WWW_AUTHENTICATE)
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def get_trip_or_404(trip_id: str, repo: TripRepo) -> Trip:
    trip = repo.get(trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Trip {trip_id} not found")
    return trip


TripDep = Annotated[Trip, Depends(get_trip_or_404)]


def get_visible_trip(trip: TripDep, user: OptionalUser) -> Trip:
    """The live trip, if this caller may see it (someone else's trip looks like it doesn't exist)."""
    if not can_see(trip.user_id, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Trip {trip.id} not found")
    return trip


VisibleTripDep = Annotated[Trip, Depends(get_visible_trip)]

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.trip import Trip
from app.repositories.trips import InMemoryTripRepository, get_trip_repository
from app.schemas.auth import User
from app.services.auth import AuthService, AuthUnavailable, get_auth_service
from app.services.history import can_see
from app.services.live import LiveHub, get_live_hub
from app.services.recording import TripRecorder, get_recorder
from app.services.speed import SpeedService, get_speed_service

TripRepo = Annotated[InMemoryTripRepository, Depends(get_trip_repository)]
Hub = Annotated[LiveHub, Depends(get_live_hub)]
Recorder = Annotated[TripRecorder, Depends(get_recorder)]
Speed = Annotated[SpeedService, Depends(get_speed_service)]
Auth = Annotated[AuthService, Depends(get_auth_service)]

bearer = HTTPBearer(auto_error=False, description="Token from POST /auth/login or /auth/register")
BearerToken = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]

_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


async def get_optional_user(auth: Auth, credentials: BearerToken) -> User | None:
    """The logged-in user, or None without an Authorization header. A bad or expired token is a 401."""
    if credentials is None:
        return None
    try:
        user = await auth.user_for_token(credentials.credentials)
    except AuthUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token - log in again", _WWW_AUTHENTICATE)
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


async def get_current_user(user: OptionalUser) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Log in first (Authorization: Bearer <token>)", _WWW_AUTHENTICATE)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_trip_or_404(trip_id: str, repo: TripRepo) -> Trip:
    trip = repo.get(trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Trip {trip_id} not found")
    return trip


TripDep = Annotated[Trip, Depends(get_trip_or_404)]


def get_visible_trip(trip: TripDep, user: OptionalUser) -> Trip:
    """The in-memory trip, if this caller may see it (someone else's trip looks like it doesn't exist)."""
    if not can_see(trip.user_id, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Trip {trip.id} not found")
    return trip


VisibleTripDep = Annotated[Trip, Depends(get_visible_trip)]

from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.domain.trip import Trip
from app.repositories.trips import InMemoryTripRepository, get_trip_repository
from app.services.live import LiveHub, get_live_hub
from app.services.recording import TripRecorder, get_recorder
from app.services.speed import SpeedService, get_speed_service

TripRepo = Annotated[InMemoryTripRepository, Depends(get_trip_repository)]
Hub = Annotated[LiveHub, Depends(get_live_hub)]
Recorder = Annotated[TripRecorder, Depends(get_recorder)]
Speed = Annotated[SpeedService, Depends(get_speed_service)]


def get_trip_or_404(trip_id: str, repo: TripRepo) -> Trip:
    trip = repo.get(trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Trip {trip_id} not found")
    return trip


TripDep = Annotated[Trip, Depends(get_trip_or_404)]

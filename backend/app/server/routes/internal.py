"""Coordinator -> server (`X-Internal-Token`). Contract: app/schemas/sync.py, docs/ARCHITECTURE.md."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.sync import CloseInterruptedIn, CloseInterruptedOut, SyncResult, TripSync
from app.server.deps import Store, require_internal_token
from app.server.services.storage import StorageUnavailable

router = APIRouter(prefix="/internal", tags=["internal (coordinator -> server)"], dependencies=[Depends(require_internal_token)])


@router.post("/trips/close-interrupted")
async def close_interrupted(body: CloseInterruptedIn, store: Store) -> CloseInterruptedOut:
    """The coordinator just started: trips it left open (crash, restart) end at their last summary."""
    try:
        return CloseInterruptedOut(closed=await store.close_interrupted(body.keep))
    except StorageUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e


@router.post("/trips/{trip_id}/sync")
async def sync_trip(trip_id: str, body: TripSync, store: Store) -> SyncResult:
    """Everything new about a trip: its meta (stored once), new sections (+ images) and the running summary.
    Idempotent. 503 while Postgres is down: the coordinator keeps the data and retries."""
    if body.trip.trip_id != trip_id or any(s.trip_id != trip_id for s in body.sections):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "trip_id in the body doesn't match the URL")
    try:
        return await store.sync(trip_id, body)
    except StorageUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e

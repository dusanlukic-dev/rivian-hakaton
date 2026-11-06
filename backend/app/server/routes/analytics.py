from fastapi import APIRouter, HTTPException, status

from app.schemas.analytics import AnalyticsOverview
from app.server.deps import Store
from app.server.services.analytics import overview
from app.server.services.storage import StorageUnavailable

router = APIRouter(prefix="/analytics", tags=["analytics (server)"])


@router.get("/overview")
async def analytics_overview(store: Store) -> AnalyticsOverview:
    """For the company: scores and behavior counts of all trips, no images and no per-driver data."""
    try:
        return overview(await store.all_trips())
    except StorageUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e

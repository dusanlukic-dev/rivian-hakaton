from fastapi import APIRouter

from app.api.deps import TripRepo
from app.schemas.analytics import AnalyticsOverview
from app.services.analytics import overview

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
def analytics_overview(repo: TripRepo) -> AnalyticsOverview:
    return overview(repo.list())

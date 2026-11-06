from fastapi import APIRouter

from app.api.routes import analytics, health, live, trips

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(live.router)
api_router.include_router(trips.router)
api_router.include_router(analytics.router)

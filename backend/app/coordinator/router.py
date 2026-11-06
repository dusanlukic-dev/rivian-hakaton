"""Every coordinator route (the in-car half). Mounted under /api/v1 by app/main.py or app/coordinator/main.py."""

from fastapi import APIRouter

from app.coordinator.routes import live, model, speed, status, trips

router = APIRouter()
router.include_router(trips.router)
router.include_router(live.router)
router.include_router(model.router)
router.include_router(speed.router)
router.include_router(status.router)

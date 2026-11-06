"""Every server route (accounts, history, reports, media, analytics, coordinator ingest)."""

from fastapi import APIRouter

from app.server.routes import analytics, auth, history, internal, media

router = APIRouter()
router.include_router(auth.router)
router.include_router(history.router)
router.include_router(media.router)
router.include_router(analytics.router)
router.include_router(internal.router)

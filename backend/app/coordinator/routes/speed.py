from fastapi import APIRouter, HTTPException, status

from app.coordinator.deps import Speed, TripRepo
from app.schemas.speed import PhoneSpeedIn, SpeedStatus
from app.coordinator.services.speed import PhoneSpeedDisabled

router = APIRouter(prefix="/speed", tags=["speed (coordinator)"])


@router.get("")
async def speed_status(repo: TripRepo, speed: Speed) -> SpeedStatus:
    """Where the speed comes from right now. The app sends its GPS only if `phone_enabled` is true."""
    return speed.status(repo.active())


@router.post("")
async def report_phone_speed(body: PhoneSpeedIn, repo: TripRepo, speed: Speed) -> SpeedStatus:
    """The phone's GPS reading (~1/s while driving). Beats the mock while it is fresh (5 s)."""
    try:
        speed.report_phone(body.speed_kmh, body.lat, body.lon)
    except PhoneSpeedDisabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Phone speed is disabled (PHONE_SPEED_ENABLED=false); the backend uses its mock drive",
        ) from None
    return speed.status(repo.active())

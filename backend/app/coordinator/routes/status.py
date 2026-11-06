from typing import Any

from fastapi import APIRouter

from app.coordinator.deps import CoordinatorDep

router = APIRouter(tags=["live (coordinator)"])


@router.get("/coordinator/status")
def coordinator_status(coordinator: CoordinatorDep) -> dict[str, Any]:
    """Is the camera streaming, is a model worker connected and how fast, video cache size, server delivery."""
    return coordinator.status()

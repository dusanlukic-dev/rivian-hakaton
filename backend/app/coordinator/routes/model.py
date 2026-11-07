"""The model worker's line into the coordinator (protocol: app/coordinator/services/model_link.py)."""

from fastapi import APIRouter, WebSocket

from app.coordinator.deps import CoordinatorDep

router = APIRouter(tags=["model (coordinator)"])


@router.websocket("/model/ws")
async def model_worker(websocket: WebSocket, coordinator: CoordinatorDep) -> None:
    """The model (`rivian_model/rivian_detector.py`) connects here: frames go out as binary messages, detections come back as JSON."""
    await coordinator.model.serve(websocket)

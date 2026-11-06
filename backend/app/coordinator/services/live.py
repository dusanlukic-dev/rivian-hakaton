"""Pushes trip events to the connected mobile app(s) over WebSocket."""

import logging

from fastapi import WebSocket
from pydantic import BaseModel

from app.domain.enums import LiveEvent

logger = logging.getLogger(__name__)


def _message(event: LiveEvent, payload: BaseModel) -> dict:
    return {"type": event, "data": payload.model_dump(mode="json")}


class LiveHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        logger.info("Mobile app connected (%d client(s))", len(self._clients))

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)
        logger.info("Mobile app disconnected (%d client(s))", len(self._clients))

    async def send(self, websocket: WebSocket, event: LiveEvent, payload: BaseModel) -> None:
        await websocket.send_json(_message(event, payload))

    async def broadcast(self, event: LiveEvent, payload: BaseModel) -> None:
        message = _message(event, payload)
        for websocket in list(self._clients):
            try:
                await websocket.send_json(message)
            except Exception:  # the phone dropped off the hotspot; it will reconnect
                self.disconnect(websocket)


_hub = LiveHub()


def get_live_hub() -> LiveHub:
    return _hub

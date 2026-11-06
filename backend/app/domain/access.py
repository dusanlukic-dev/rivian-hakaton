"""Who may see a trip. A trip started while logged in belongs to that account: anyone else gets 404, as if it
didn't exist. A trip started without login is visible to everyone. The car's live channel (WS, telemetry,
ending a trip) stays open: it's the car's own network."""

from typing import Protocol


class _HasUserId(Protocol):
    user_id: str


def can_see(owner_id: str | None, user: _HasUserId | None) -> bool:
    return owner_id is None or (user is not None and user.user_id == owner_id)

"""How the coordinator talks to the server part: plain HTTP, the same in one process or across machines.

    SERVER_URL empty  -> in-process: httpx.ASGITransport calls the server routes of this very app, no socket.
    SERVER_URL set    -> over the network, e.g. http://10.0.0.5:8001/api/v1 (split deployment, Docker later).

Either way the coordinator only knows the server's API: `/internal/*` (header X-Internal-Token) to deliver
trips and sections, and the public `GET /auth/me` to find out who a phone's token belongs to. It never
touches the database or S3 itself.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import FastAPI

from app.core.config import Settings
from app.schemas.auth import User
from app.schemas.sync import CloseInterruptedIn, CloseInterruptedOut, SyncResult, TripSync

USER_CACHE_S = 30.0


class ServerUnavailable(Exception):
    """The server didn't answer, or answered 5xx (database down...). Try again later."""


class ServerRejected(Exception):
    """The server answered 4xx: the request itself is wrong, retrying won't help."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{status}: {detail}")
        self.status = status


class ServerClient:
    def __init__(self, http: httpx.AsyncClient, internal_token: str, description: str) -> None:
        self._http = http
        self._headers = {"X-Internal-Token": internal_token}
        self.description = description
        self._users: dict[str, tuple[float, User | None]] = {}

    @classmethod
    def for_app(cls, app: FastAPI, settings: Settings) -> ServerClient:
        """In-process (SERVER_URL empty) or remote (SERVER_URL set)."""
        if settings.server_url:
            base = settings.server_url.rstrip("/")
            http = httpx.AsyncClient(base_url=base, timeout=httpx.Timeout(15.0, connect=3.0))
            return cls(http, settings.internal_token, base)
        transport = httpx.ASGITransport(app=app)
        http = httpx.AsyncClient(transport=transport, base_url=f"http://in-process{settings.api_prefix}", timeout=30.0)
        return cls(http, settings.internal_token, "in-process")

    async def aclose(self) -> None:
        await self._http.aclose()

    async def sync(self, trip_id: str, body: TripSync) -> SyncResult:
        data = await self._request(
            "POST", f"/internal/trips/{trip_id}/sync", json=body.model_dump(mode="json"), headers=self._headers
        )
        return SyncResult.model_validate(data)

    async def close_interrupted(self, keep: list[str]) -> int:
        body = CloseInterruptedIn(keep=keep).model_dump(mode="json")
        data = await self._request("POST", "/internal/trips/close-interrupted", json=body, headers=self._headers)
        return CloseInterruptedOut.model_validate(data).closed

    async def user_for_token(self, token: str) -> User | None:
        """The account behind a phone's bearer token; None if the token is wrong or expired.

        Answers are re-checked after USER_CACHE_S. While the server is unreachable the last answer for this token
        is used, however old (the car keeps working without the server); ServerUnavailable only for a token
        never checked before.
        """
        now = time.monotonic()
        cached = self._users.get(token)
        if cached is not None and now - cached[0] < USER_CACHE_S:
            return cached[1]
        try:
            data = await self._request("GET", "/auth/me", headers={"Authorization": f"Bearer {token}"})
            user = User.model_validate(data)
        except ServerUnavailable:
            if cached is not None:
                return cached[1]
            raise
        except ServerRejected as e:
            if e.status != 401:
                raise
            user = None
        if len(self._users) > 256:
            self._users.clear()
        self._users[token] = (now, user)
        return user

    def forget_token(self, token: str) -> None:
        self._users.pop(token, None)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._http.request(method, path.lstrip("/"), **kwargs)
        except httpx.HTTPError as e:
            raise ServerUnavailable(f"{type(e).__name__}: {e}") from e
        if response.status_code >= 500:
            raise ServerUnavailable(f"{response.status_code}: {_detail(response)}")
        if response.status_code >= 400:
            raise ServerRejected(response.status_code, _detail(response))
        return response.json() if response.content else None


def _detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("detail"))[:300]
    except Exception:
        return response.text[:300]

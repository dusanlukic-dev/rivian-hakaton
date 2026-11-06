"""The backend's two parts (docs/ARCHITECTURE.md), as one process or two.

    role "all"          coordinator + server in one process, one port (the demo: `python run.py`)
    role "coordinator"  the in-car part alone: `python run.py --role coordinator` (needs SERVER_URL)
    role "server"       the storage/report part alone: `python run.py --role server --port 8001`

Even in one process the coordinator reaches the server only through its HTTP API (in-process transport),
so splitting them is a configuration change, not a code change.
"""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.coordinator.router import router as coordinator_router
from app.coordinator.services.coordinator import get_coordinator
from app.coordinator.services.server_client import ServerClient
from app.coordinator.services.speed import get_speed_service
from app.core.config import get_settings
from app.core.health import router as health_router
from app.server.repositories.database import get_database
from app.server.router import router as server_router
from app.server.services.storage import get_trip_store

Role = Literal["all", "coordinator", "server"]


def _configure_logging() -> None:
    """Our own `app.*` loggers at INFO next to uvicorn's output (SQLAlchemy and boto stay quiet)."""
    log = logging.getLogger("app")
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)-9s %(name)s: %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False


def _lifespan(role: Role) -> Callable[[FastAPI], AsyncIterator[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Resolved like the routes' dependencies, so tests can swap them via app.dependency_overrides.
        def resolve(dependency):
            return app.dependency_overrides.get(dependency, dependency)()

        settings = get_settings()
        async with AsyncExitStack() as stack:
            if role in ("all", "server"):
                database = resolve(get_database)  # doesn't connect until first used
                stack.push_async_callback(database.close)
                await resolve(get_trip_store).start()
            if role in ("all", "coordinator"):
                if role == "coordinator" and not settings.server_url:
                    raise RuntimeError("The coordinator alone needs SERVER_URL (e.g. http://127.0.0.1:8001/api/v1)")
                resolve(get_speed_service)  # fails fast on a bad SPEED_SCENARIO
                client = ServerClient.for_app(app, settings)
                stack.push_async_callback(client.aclose)
                coordinator = resolve(get_coordinator)
                await coordinator.start(client)
                stack.push_async_callback(coordinator.stop)  # runs first: delivers to the server, then it closes
            yield

    return lifespan


def create_app(role: Role = "all") -> FastAPI:
    _configure_logging()
    settings = get_settings()
    title = {"all": settings.app_name, "coordinator": f"{settings.app_name} - coordinator",
             "server": f"{settings.app_name} - server"}[role]
    app = FastAPI(title=title, version="0.4.0", lifespan=_lifespan(role))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix=settings.api_prefix)
    if role in ("all", "coordinator"):
        app.include_router(coordinator_router, prefix=settings.api_prefix)
    if role in ("all", "server"):
        app.include_router(server_router, prefix=settings.api_prefix)
    return app


app = create_app("all")

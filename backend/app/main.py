import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.repositories.database import get_database
from app.services.recording import get_recorder
from app.services.speed import get_speed_service


def _configure_logging() -> None:
    """Our own `app.*` loggers at INFO next to uvicorn's output (SQLAlchemy and boto stay quiet)."""
    log = logging.getLogger("app")
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)-9s %(name)s: %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Resolved like the routes' dependencies, so tests can swap them via app.dependency_overrides.
    def resolve(dependency):
        return app.dependency_overrides.get(dependency, dependency)()

    resolve(get_speed_service)  # fails fast on a bad SPEED_SCENARIO
    database = resolve(get_database)  # accounts + recording; doesn't connect until first used
    recorder = resolve(get_recorder)
    await recorder.start()
    try:
        yield
    finally:
        await recorder.stop()
        await database.close()


def create_app() -> FastAPI:
    _configure_logging()
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()

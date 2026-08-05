from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.routes.health import router as health_router
from app.api.routes.metrics import router as metrics_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.services.health import HealthService


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(resolved_settings)
        engine = create_engine(resolved_settings)
        redis = Redis.from_url(resolved_settings.redis_url, decode_responses=True)
        application.state.engine = engine
        application.state.session_factory = create_session_factory(engine)
        application.state.redis = redis
        application.state.health_service = HealthService(
            engine=engine,
            redis=redis,
            timeout_seconds=resolved_settings.dependency_timeout_seconds,
        )
        try:
            yield
        finally:
            await redis.aclose()
            await engine.dispose()

    application = FastAPI(
        title="Telegram Job Match Bot",
        version="0.1.0",
        debug=resolved_settings.app_debug,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.include_router(health_router)
    if resolved_settings.metrics_enabled:
        application.include_router(metrics_router)
    return application


app = create_app()

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.routes.health import router as health_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.telegram import router as telegram_router
from app.bot.factory import create_bot, create_dispatcher
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.services.health import HealthService
from app.services.onboarding import OnboardingService
from app.services.profiles import ProfileService
from app.services.queue import ArqResumeQueue
from app.services.resumes import ResumeService
from app.services.storage import create_storage
from app.services.telegram_users import TelegramUpdateService, TelegramUserService


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
        application.state.telegram_user_service = TelegramUserService(
            application.state.session_factory, resolved_settings
        )
        application.state.telegram_update_service = TelegramUpdateService(
            application.state.session_factory, resolved_settings
        )
        application.state.resume_service = ResumeService(
            application.state.session_factory,
            create_storage(resolved_settings),
            resolved_settings,
        )
        application.state.resume_queue = ArqResumeQueue(resolved_settings.redis_url)
        application.state.profile_service = ProfileService(application.state.session_factory)
        application.state.onboarding_service = OnboardingService(application.state.session_factory)
        application.state.bot = (
            create_bot(resolved_settings) if resolved_settings.has_telegram_token else None
        )
        application.state.dispatcher = create_dispatcher() if application.state.bot else None
        try:
            yield
        finally:
            if application.state.bot is not None:
                await application.state.bot.session.close()
            await application.state.resume_queue.close()
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
    application.include_router(telegram_router)
    if resolved_settings.metrics_enabled:
        application.include_router(metrics_router)
    return application


app = create_app()

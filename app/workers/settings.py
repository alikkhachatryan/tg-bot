from typing import Any, ClassVar

from arq.connections import RedisSettings

from app.bot.factory import create_bot
from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.services.storage import create_storage
from app.workers.tasks import process_resume, worker_healthcheck


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    ctx["engine"] = engine
    ctx["sessions"] = create_session_factory(engine)
    ctx["storage"] = create_storage(settings)
    ctx["bot"] = create_bot(settings) if settings.has_telegram_token else None


async def shutdown(ctx: dict[str, Any]) -> None:
    bot = ctx.get("bot")
    if bot is not None:
        await bot.session.close()
    await ctx["engine"].dispose()


class WorkerSettings:
    functions: ClassVar[list[object]] = [worker_healthcheck, process_resume]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 20
    job_timeout = 300
    max_tries = 3
    health_check_interval = 30

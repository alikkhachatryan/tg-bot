from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.sources import create_vacancy_sources
from app.workers.tasks import ingest_vacancies, scheduler_heartbeat


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    ctx["engine"] = engine
    ctx["sessions"] = create_session_factory(engine)
    ctx["vacancy_sources"] = create_vacancy_sources(settings)


async def shutdown(ctx: dict[str, Any]) -> None:
    for source in ctx["vacancy_sources"]:
        await source.close()
    await ctx["engine"].dispose()


class SchedulerSettings:
    functions: ClassVar[list[object]] = [scheduler_heartbeat, ingest_vacancies]
    cron_jobs: ClassVar[list[object]] = [
        cron(scheduler_heartbeat, minute={0, 15, 30, 45}, unique=True),
        cron(ingest_vacancies, hour={0, 6, 12, 18}, minute=10, unique=True),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 1
    job_timeout = 600
    max_tries = 2

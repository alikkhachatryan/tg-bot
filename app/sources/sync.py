import asyncio

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.services.vacancies import VacancyIngestionService
from app.sources.factory import create_vacancy_sources

logger = structlog.get_logger()


async def sync_once() -> int:
    settings = get_settings()
    configure_logging(settings)
    engine = create_engine(settings)
    sources = create_vacancy_sources(settings)
    failed = 0
    try:
        service = VacancyIngestionService(create_session_factory(engine))
        for source in sources:
            run = await service.ingest_source(source)
            logger.info(
                "vacancy_source_sync_finished",
                source=source.name,
                status=run.status,
                fetched_count=run.fetched_count,
                stored_count=run.stored_count,
                error_code=run.error_code,
            )
            failed += run.status != "completed"
    finally:
        for source in sources:
            await source.close()
        await engine.dispose()
    return failed


def main() -> None:
    raise SystemExit(asyncio.run(sync_once()))


if __name__ == "__main__":
    main()

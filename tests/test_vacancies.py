from typing import Any

from sqlalchemy import func, select

from app.db.models.vacancy import Vacancy, VacancyIngestionRun, VacancyOrigin
from app.services.vacancies import VacancyIngestionService
from app.sources.base import VacancySourceError
from app.sources.schemas import VacancyRecord
from app.workers.tasks import ingest_vacancies


class FakeSource:
    def __init__(self, name: str, records: list[VacancyRecord]) -> None:
        self.name = name
        self.records = records

    async def fetch(self) -> list[VacancyRecord]:
        return self.records

    async def close(self) -> None:
        return None


class BrokenSource(FakeSource):
    async def fetch(self) -> list[VacancyRecord]:
        raise VacancySourceError("rate_limited")


def vacancy_record(source: str, external_id: str) -> VacancyRecord:
    return VacancyRecord(
        source=source,
        external_id=external_id,
        title="Senior Python Developer",
        company="Armenian Tech",
        description="Build reliable Python services",
        location="Yerevan, Armenia",
        country_code="AM",
        workplace_type="hybrid",
        canonical_url=f"https://{source}.example/{external_id}",
        attribution=source.title(),
    )


async def test_ingestion_merges_duplicates_and_preserves_origins(sqlite_sessions: Any) -> None:
    service = VacancyIngestionService(sqlite_sessions)

    first = await service.ingest_source(
        FakeSource("greenhouse", [vacancy_record("greenhouse", "1")])
    )
    second = await service.ingest_source(FakeSource("lever", [vacancy_record("lever", "2")]))

    assert first.status == "completed"
    assert second.status == "completed"
    async with sqlite_sessions() as session:
        vacancy_count = await session.scalar(select(func.count()).select_from(Vacancy))
        origin_count = await session.scalar(select(func.count()).select_from(VacancyOrigin))
    assert vacancy_count == 1
    assert origin_count == 2


async def test_reingestion_updates_existing_origin(sqlite_sessions: Any) -> None:
    service = VacancyIngestionService(sqlite_sessions)
    source = FakeSource("hh", [vacancy_record("hh", "42")])

    await service.ingest_source(source)
    await service.ingest_source(source)

    async with sqlite_sessions() as session:
        origin_count = await session.scalar(select(func.count()).select_from(VacancyOrigin))
        runs = list(await session.scalars(select(VacancyIngestionRun)))
    assert origin_count == 1
    assert len(runs) == 2

    latest = await service.latest()
    assert len(latest) == 1
    assert latest[0].title == "Senior Python Developer"


async def test_changed_origin_is_remapped_to_existing_duplicate(sqlite_sessions: Any) -> None:
    service = VacancyIngestionService(sqlite_sessions)
    first = vacancy_record("hh", "1")
    second = vacancy_record("lever", "2").model_copy(update={"title": "QA Engineer"})

    await service.ingest_source(FakeSource("hh", [first]))
    await service.ingest_source(FakeSource("lever", [second]))
    changed = first.model_copy(update={"title": "QA Engineer"})
    await service.ingest_source(FakeSource("hh", [changed]))

    async with sqlite_sessions() as session:
        vacancy_count = await session.scalar(select(func.count()).select_from(Vacancy))
        origin_count = await session.scalar(select(func.count()).select_from(VacancyOrigin))
    assert vacancy_count == 1
    assert origin_count == 2


async def test_source_failure_is_recorded_without_raising(sqlite_sessions: Any) -> None:
    service = VacancyIngestionService(sqlite_sessions)

    run = await service.ingest_source(BrokenSource("broken", []))

    assert run.status == "failed"
    assert run.error_code == "rate_limited"


async def test_source_name_mismatch_is_rejected(sqlite_sessions: Any) -> None:
    service = VacancyIngestionService(sqlite_sessions)

    run = await service.ingest_source(FakeSource("hh", [vacancy_record("lever", "42")]))

    assert run.status == "failed"
    assert run.error_code == "source_mismatch"


async def test_worker_isolates_source_results(sqlite_sessions: Any) -> None:
    ctx = {
        "sessions": sqlite_sessions,
        "vacancy_sources": [
            BrokenSource("broken", []),
            FakeSource("lever", [vacancy_record("lever", "ok")]),
        ],
    }

    result = await ingest_vacancies(ctx)

    assert result == {"broken": "failed", "lever": "completed"}

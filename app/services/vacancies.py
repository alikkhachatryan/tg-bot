from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.vacancy import Vacancy, VacancyIngestionRun, VacancyOrigin
from app.sources.base import VacancySource, VacancySourceError
from app.sources.normalize import vacancy_content_hash, vacancy_fingerprint
from app.sources.schemas import VacancyRecord

logger = structlog.get_logger()


class VacancyIngestionService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def latest(self, limit: int = 5) -> list[Vacancy]:
        async with self._sessions() as session:
            return list(
                await session.scalars(
                    select(Vacancy)
                    .order_by(
                        Vacancy.published_at.desc().nullslast(),
                        Vacancy.last_seen_at.desc(),
                    )
                    .limit(limit)
                )
            )

    async def ingest_source(self, source: VacancySource) -> VacancyIngestionRun:
        run = VacancyIngestionRun(source=source.name, status="running")
        async with self._sessions.begin() as session:
            session.add(run)
            await session.flush()
            run_id = run.id

        try:
            records = await source.fetch()
            if any(record.source != source.name for record in records):
                raise VacancySourceError("source_mismatch")
            stored_count = await self.store(records)
        except VacancySourceError as exc:
            return await self._finish_run(run_id, "failed", error_code=exc.code)
        except Exception as exc:
            logger.exception(
                "vacancy_ingestion_failed", source=source.name, error_type=type(exc).__name__
            )
            return await self._finish_run(run_id, "failed", error_code="unexpected_error")
        return await self._finish_run(
            run_id,
            "completed",
            fetched_count=len(records),
            stored_count=stored_count,
        )

    async def store(self, records: list[VacancyRecord]) -> int:
        now = datetime.now(UTC)
        async with self._sessions.begin() as session:
            for record in records:
                await self._store_one(session, record, now)
        return len(records)

    async def _store_one(self, session: AsyncSession, record: VacancyRecord, now: datetime) -> None:
        origin = await session.scalar(
            select(VacancyOrigin).where(
                VacancyOrigin.source == record.source,
                VacancyOrigin.external_id == record.external_id,
            )
        )
        fingerprint = vacancy_fingerprint(record)
        content_hash = vacancy_content_hash(record)
        existing = await session.get(Vacancy, origin.vacancy_id) if origin is not None else None
        duplicate = await session.scalar(select(Vacancy).where(Vacancy.fingerprint == fingerprint))
        vacancy = duplicate or existing
        if vacancy is None:
            vacancy = Vacancy(fingerprint=fingerprint, **_vacancy_values(record), last_seen_at=now)
            session.add(vacancy)
            await session.flush()
        else:
            for key, value in _vacancy_values(record).items():
                setattr(vacancy, key, value)
            vacancy.fingerprint = fingerprint
            vacancy.last_seen_at = now

        if origin is None:
            session.add(
                VacancyOrigin(
                    vacancy_id=vacancy.id,
                    source=record.source,
                    external_id=record.external_id,
                    source_url=record.canonical_url,
                    content_hash=content_hash,
                    attribution=record.attribution,
                    last_seen_at=now,
                )
            )
        else:
            previous_vacancy = existing
            origin.vacancy_id = vacancy.id
            origin.source_url = record.canonical_url
            origin.content_hash = content_hash
            origin.attribution = record.attribution
            origin.last_seen_at = now
            if previous_vacancy is not None and previous_vacancy.id != vacancy.id:
                other_origin = await session.scalar(
                    select(VacancyOrigin.id).where(
                        VacancyOrigin.vacancy_id == previous_vacancy.id,
                        VacancyOrigin.id != origin.id,
                    )
                )
                if other_origin is None:
                    await session.delete(previous_vacancy)

    async def _finish_run(
        self,
        run_id: UUID,
        status: str,
        *,
        fetched_count: int = 0,
        stored_count: int = 0,
        error_code: str | None = None,
    ) -> VacancyIngestionRun:
        async with self._sessions.begin() as session:
            await session.execute(
                update(VacancyIngestionRun)
                .where(VacancyIngestionRun.id == run_id)
                .values(
                    status=status,
                    fetched_count=fetched_count,
                    stored_count=stored_count,
                    error_code=error_code,
                    completed_at=datetime.now(UTC),
                )
            )
        async with self._sessions() as session:
            result = await session.get(VacancyIngestionRun, run_id)
        if result is None:
            raise RuntimeError("Ingestion run disappeared")
        return result


def _vacancy_values(record: VacancyRecord) -> dict[str, object]:
    return {
        "title": record.title,
        "company": record.company,
        "description": record.description,
        "location": record.location,
        "country_code": record.country_code,
        "workplace_type": record.workplace_type,
        "employment_type": record.employment_type,
        "remote_scope": record.remote_scope,
        "salary_min": record.salary_min,
        "salary_max": record.salary_max,
        "salary_currency": record.salary_currency,
        "canonical_url": record.canonical_url,
        "apply_url": record.apply_url,
        "published_at": record.published_at,
        "expires_at": record.expires_at,
    }

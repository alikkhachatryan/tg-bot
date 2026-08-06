from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models.vacancy import Vacancy, VacancyOrigin
from app.services.telegram_vacancies import TelegramVacancyService, telegram_message_url
from app.services.vacancies import VacancyIngestionService

VACANCY_TEXT = """Vacancy: Senior PHP Developer
Company: Example Tech
Location: Yerevan, Armenia
We are hiring a PHP developer. Requirements: PHP, Bitrix, SQL and Git. Remote work is available.
Apply: https://example.com/apply
"""


async def test_allowed_channel_post_is_stored_and_edit_updates_it(
    sqlite_sessions: Any,
) -> None:
    ingestion = VacancyIngestionService(sqlite_sessions)
    service = TelegramVacancyService(
        ingestion,
        Settings(_env_file=None, telegram_vacancy_chat_ids="-100123"),
    )

    first = await service.ingest(
        chat_id=-100123,
        chat_type="channel",
        chat_title="Armenia Jobs",
        chat_username="armenia_jobs",
        message_id=42,
        text=VACANCY_TEXT,
        published_at=datetime.now(UTC),
    )
    edited = await service.ingest(
        chat_id=-100123,
        chat_type="channel",
        chat_title="Armenia Jobs",
        chat_username="armenia_jobs",
        message_id=42,
        text=VACANCY_TEXT.replace("Senior PHP Developer", "Lead PHP Developer"),
        published_at=datetime.now(UTC),
    )

    assert first.stored is True
    assert edited.stored is True
    async with sqlite_sessions() as session:
        vacancy_count = await session.scalar(select(func.count()).select_from(Vacancy))
        origin_count = await session.scalar(select(func.count()).select_from(VacancyOrigin))
        stored = await session.scalar(select(Vacancy))
        origin = await session.scalar(select(VacancyOrigin))
    assert vacancy_count == 1
    assert origin_count == 1
    assert stored is not None and stored.title == "Lead PHP Developer"
    assert stored.country_code == "AM"
    assert stored.workplace_type == "remote"
    assert stored.apply_url == "https://example.com/apply"
    assert origin is not None and origin.external_id == "-100123:42"
    assert origin.source_url == "https://t.me/armenia_jobs/42"


async def test_unapproved_or_non_vacancy_messages_are_ignored() -> None:
    ingestion = SimpleNamespace(store=AsyncMock())
    service = TelegramVacancyService(
        ingestion,
        Settings(_env_file=None, telegram_vacancy_chat_usernames="@approved_jobs"),
    )

    denied = await service.ingest(
        chat_id=-1001,
        chat_type="channel",
        chat_title="Other",
        chat_username="other_jobs",
        message_id=1,
        text=VACANCY_TEXT,
        published_at=datetime.now(UTC),
    )
    chatter = await service.ingest(
        chat_id=-1002,
        chat_type="supergroup",
        chat_title="Approved",
        chat_username="approved_jobs",
        message_id=2,
        text="Сегодня много работы, обсудим текущие задачи команды после обеда и созвонимся.",
        published_at=datetime.now(UTC),
    )

    assert denied.reason == "not_allowed"
    assert chatter.reason == "not_a_vacancy"
    ingestion.store.assert_not_awaited()


async def test_private_basic_group_without_message_url_is_ignored() -> None:
    ingestion = SimpleNamespace(store=AsyncMock())
    service = TelegramVacancyService(
        ingestion,
        Settings(_env_file=None, telegram_vacancy_chat_ids="-123"),
    )

    result = await service.ingest(
        chat_id=-123,
        chat_type="group",
        chat_title="Private jobs",
        chat_username=None,
        message_id=7,
        text=VACANCY_TEXT,
        published_at=datetime.now(UTC),
    )

    assert result.reason == "message_url_unavailable"
    ingestion.store.assert_not_awaited()


def test_telegram_message_urls_support_public_and_private_supergroups() -> None:
    assert (
        telegram_message_url(chat_id=-100123, chat_type="channel", username="@jobs", message_id=5)
        == "https://t.me/jobs/5"
    )
    assert (
        telegram_message_url(chat_id=-100123, chat_type="supergroup", username=None, message_id=5)
        == "https://t.me/c/123/5"
    )
    assert (
        telegram_message_url(chat_id=-123, chat_type="group", username=None, message_id=5) is None
    )

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models.telegram import ConversationState, ProcessedTelegramUpdate, TelegramAccount
from app.services.telegram_users import (
    BetaAccessDeniedError,
    TelegramIdentity,
    TelegramUpdateService,
    TelegramUserService,
)


def beta_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        beta_mode=True,
        beta_telegram_ids="100",
        telegram_update_claim_timeout_seconds=30,
    )


async def test_registration_is_durable_and_updates_identity(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    service = TelegramUserService(sqlite_sessions, beta_settings())
    user_id = await service.register(TelegramIdentity(100, username="old", locale="ru"))
    repeated_id = await service.register(TelegramIdentity(100, username="new", locale="ru"))

    assert repeated_id == user_id
    async with sqlite_sessions() as session:
        account = await session.scalar(select(TelegramAccount))
        state = await session.get(ConversationState, user_id)
    assert account is not None and account.username == "new"
    assert state is not None and state.state == "awaiting_consent"


async def test_beta_allowlist_is_enforced(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    service = TelegramUserService(sqlite_sessions, beta_settings())

    with pytest.raises(BetaAccessDeniedError):
        await service.register(TelegramIdentity(999))


async def test_consent_is_versioned_and_idempotent(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    service = TelegramUserService(sqlite_sessions, beta_settings())
    user_id = await service.register(TelegramIdentity(100))

    assert await service.has_required_consent(user_id) is False
    await service.grant_required_consent(user_id, 10)
    await service.grant_required_consent(user_id, 11)

    assert await service.has_required_consent(user_id) is True
    async with sqlite_sessions() as session:
        state = await session.get(ConversationState, user_id)
    assert state is not None and state.state == "awaiting_resume"


async def test_update_claim_complete_and_release(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    service = TelegramUpdateService(sqlite_sessions, beta_settings())

    assert await service.claim(1) is True
    assert await service.claim(1) is False
    await service.complete(1)
    assert await service.claim(1) is False

    assert await service.claim(2) is True
    await service.release(2)
    assert await service.claim(2) is True


async def test_stale_processing_claim_can_be_recovered(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    service = TelegramUpdateService(sqlite_sessions, beta_settings())
    async with sqlite_sessions.begin() as session:
        session.add(
            ProcessedTelegramUpdate(
                update_id=3,
                status="processing",
                received_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        )

    assert await service.claim(3) is True

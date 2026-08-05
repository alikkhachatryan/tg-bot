from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models.telegram import (
    Consent,
    ConversationState,
    ProcessedTelegramUpdate,
    TelegramAccount,
    User,
)

REQUIRED_CONSENT = "personal_data_and_external_ai"


class BetaAccessDeniedError(Exception):
    """The Telegram account is not on the closed-beta allowlist."""


@dataclass(frozen=True, slots=True)
class TelegramIdentity:
    telegram_user_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    locale: str | None = None


class TelegramUserService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self._sessions = sessions
        self._settings = settings

    def ensure_beta_access(self, telegram_user_id: int) -> None:
        if self._settings.beta_mode and telegram_user_id not in self._settings.beta_user_ids:
            raise BetaAccessDeniedError

    async def register(self, identity: TelegramIdentity) -> UUID:
        self.ensure_beta_access(identity.telegram_user_id)
        try:
            return await self._register(identity)
        except IntegrityError:
            return await self._existing_user_id(identity.telegram_user_id)

    async def _register(self, identity: TelegramIdentity) -> UUID:
        async with self._sessions.begin() as session:
            account = await session.scalar(
                select(TelegramAccount).where(
                    TelegramAccount.telegram_user_id == identity.telegram_user_id
                )
            )
            if account is not None:
                account.username = identity.username
                account.first_name = identity.first_name
                account.last_name = identity.last_name
                return account.user_id

            user = User(locale=identity.locale)
            session.add(user)
            await session.flush()
            session.add(
                TelegramAccount(
                    user_id=user.id,
                    telegram_user_id=identity.telegram_user_id,
                    username=identity.username,
                    first_name=identity.first_name,
                    last_name=identity.last_name,
                )
            )
            session.add(ConversationState(user_id=user.id, state="awaiting_consent", data={}))
            return user.id

    async def _existing_user_id(self, telegram_user_id: int) -> UUID:
        async with self._sessions() as session:
            user_id = await session.scalar(
                select(TelegramAccount.user_id).where(
                    TelegramAccount.telegram_user_id == telegram_user_id
                )
            )
        if user_id is None:
            raise RuntimeError("Telegram registration conflict could not be resolved")
        return user_id

    async def grant_required_consent(self, user_id: UUID, update_id: int | None) -> None:
        async with self._sessions.begin() as session:
            consent = await session.scalar(
                select(Consent).where(
                    Consent.user_id == user_id,
                    Consent.consent_type == REQUIRED_CONSENT,
                    Consent.policy_version == self._settings.privacy_policy_version,
                )
            )
            if consent is None:
                session.add(
                    Consent(
                        user_id=user_id,
                        consent_type=REQUIRED_CONSENT,
                        policy_version=self._settings.privacy_policy_version,
                        source_update_id=update_id,
                    )
                )
            else:
                consent.revoked_at = None
                consent.source_update_id = update_id
            await session.execute(
                update(ConversationState)
                .where(ConversationState.user_id == user_id)
                .values(state="awaiting_resume", data={})
            )

    async def has_required_consent(self, user_id: UUID) -> bool:
        async with self._sessions() as session:
            consent_id = await session.scalar(
                select(Consent.id).where(
                    Consent.user_id == user_id,
                    Consent.consent_type == REQUIRED_CONSENT,
                    Consent.policy_version == self._settings.privacy_policy_version,
                    Consent.revoked_at.is_(None),
                )
            )
        return consent_id is not None


class TelegramUpdateService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self._sessions = sessions
        self._claim_timeout = timedelta(seconds=settings.telegram_update_claim_timeout_seconds)

    async def claim(self, update_id: int) -> bool:
        now = datetime.now(UTC)
        try:
            async with self._sessions.begin() as session:
                row = await session.get(ProcessedTelegramUpdate, update_id)
                if row is not None:
                    received_at = row.received_at
                    if received_at.tzinfo is None:
                        received_at = received_at.replace(tzinfo=UTC)
                    if row.status == "processing" and received_at < now - self._claim_timeout:
                        row.received_at = now
                        return True
                    return False
                session.add(
                    ProcessedTelegramUpdate(
                        update_id=update_id,
                        status="processing",
                        received_at=now,
                    )
                )
        except IntegrityError:
            return False
        return True

    async def complete(self, update_id: int) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(ProcessedTelegramUpdate)
                .where(ProcessedTelegramUpdate.update_id == update_id)
                .values(status="processed", processed_at=datetime.now(UTC))
            )

    async def release(self, update_id: int) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                delete(ProcessedTelegramUpdate).where(
                    ProcessedTelegramUpdate.update_id == update_id,
                    ProcessedTelegramUpdate.status == "processing",
                )
            )

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from aiogram import Bot
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.resume import ResumeDocument
from app.db.models.telegram import TelegramAccount
from app.services.resume_extraction import ResumeTextMissingError, extract_resume_text
from app.services.storage import PrivateStorage

logger = structlog.get_logger()


async def worker_healthcheck(ctx: dict[str, Any]) -> str:
    return "ok"


async def scheduler_heartbeat(ctx: dict[str, Any]) -> str:
    return "ok"


async def process_resume(ctx: dict[str, Any], resume_id: str) -> str:
    sessions: async_sessionmaker[AsyncSession] = ctx["sessions"]
    storage: PrivateStorage = ctx["storage"]
    bot: Bot | None = ctx.get("bot")
    identifier = UUID(resume_id)

    async with sessions.begin() as session:
        claimed = await session.scalar(
            update(ResumeDocument)
            .where(ResumeDocument.id == identifier, ResumeDocument.status == "queued")
            .values(status="processing", error_code=None)
            .returning(ResumeDocument.id)
        )
    if claimed is None:
        return "skipped"

    async with sessions() as session:
        document = await session.get(ResumeDocument, identifier)
    if document is None:
        return "skipped"

    try:
        data = await storage.get(document.storage_key)
        text = extract_resume_text(data, document.media_type)
    except ResumeTextMissingError:
        await _finish_resume(sessions, identifier, "failed", "text_layer_missing")
        await _notify(
            sessions,
            bot,
            document.user_id,
            "Не удалось найти текст в PDF. Загрузите текстовый PDF или DOCX.",
        )
        return "text_layer_missing"
    except Exception as exc:
        logger.exception(
            "resume_processing_failed", resume_id=resume_id, error_type=type(exc).__name__
        )
        await _finish_resume(sessions, identifier, "failed", "processing_error")
        await _notify(
            sessions,
            bot,
            document.user_id,
            "Не удалось обработать резюме. Попробуйте другой PDF или DOCX.",
        )
        return "failed"

    async with sessions.begin() as session:
        await session.execute(
            update(ResumeDocument)
            .where(ResumeDocument.id == identifier)
            .values(
                status="processed",
                extracted_text=text,
                error_code=None,
                processed_at=datetime.now(UTC),
            )
        )
    await _notify(
        sessions,
        bot,
        document.user_id,
        "Резюме обработано. Следующий шаг — создание профиля.",
    )
    return "processed"


async def _finish_resume(
    sessions: async_sessionmaker[AsyncSession], resume_id: UUID, status: str, error_code: str
) -> None:
    async with sessions.begin() as session:
        await session.execute(
            update(ResumeDocument)
            .where(ResumeDocument.id == resume_id)
            .values(status=status, error_code=error_code, processed_at=datetime.now(UTC))
        )


async def _notify(
    sessions: async_sessionmaker[AsyncSession], bot: Bot | None, user_id: UUID, text: str
) -> None:
    if bot is None:
        return
    async with sessions() as session:
        telegram_user_id = await session.scalar(
            select(TelegramAccount.telegram_user_id).where(TelegramAccount.user_id == user_id)
        )
    if telegram_user_id is not None:
        try:
            await bot.send_message(telegram_user_id, text)
        except Exception as exc:
            logger.warning("resume_notification_failed", error_type=type(exc).__name__)

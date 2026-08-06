from datetime import UTC, datetime
from html import escape
from typing import Any
from uuid import UUID

import structlog
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.deepseek import PROMPT_VERSION
from app.ai.provider import AIProvider, AIProviderError
from app.bot.keyboards import profile_review_keyboard
from app.db.models.profile import ResumeParseRun
from app.db.models.resume import ResumeDocument
from app.db.models.telegram import TelegramAccount
from app.services.profiles import ProfileService
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
    if "ai_provider" in ctx:
        await parse_resume_profile(ctx, identifier)
    else:
        await _notify(
            sessions,
            bot,
            document.user_id,
            "Резюме обработано. Следующий шаг — создание профиля.",
        )
    return "processed"


async def parse_resume_profile(ctx: dict[str, Any], resume_id: UUID) -> str:
    sessions: async_sessionmaker[AsyncSession] = ctx["sessions"]
    provider: AIProvider = ctx["ai_provider"]
    bot: Bot | None = ctx.get("bot")
    async with sessions() as session:
        document = await session.get(ResumeDocument, resume_id)
    if document is None or not document.extracted_text:
        return "skipped"

    run = ResumeParseRun(
        resume_id=resume_id,
        provider=provider.name,
        model=provider.model,
        prompt_version=PROMPT_VERSION,
        status="processing",
    )
    async with sessions.begin() as session:
        session.add(run)
        await session.flush()
        run_id = run.id

    try:
        result = await provider.parse_resume(document.extracted_text)
        profile = await ProfileService(sessions).save_draft(
            document.user_id, resume_id, result.profile
        )
    except AIProviderError as exc:
        await _finish_parse_run(sessions, run_id, "failed", exc.code)
        await _notify(
            sessions,
            bot,
            document.user_id,
            "AI-сервис временно не смог разобрать резюме. Попробуйте обработку позже.",
        )
        return "ai_failed"
    except Exception as exc:
        logger.exception(
            "resume_ai_parse_failed", resume_id=str(resume_id), error_type=type(exc).__name__
        )
        await _finish_parse_run(sessions, run_id, "failed", "processing_error")
        await _notify(
            sessions,
            bot,
            document.user_id,
            "Не удалось создать профиль. Попробуйте обработку позже.",
        )
        return "failed"

    async with sessions.begin() as session:
        await session.execute(
            update(ResumeParseRun)
            .where(ResumeParseRun.id == run_id)
            .values(
                status="completed",
                provider_request_id=result.request_id,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                completed_at=datetime.now(UTC),
            )
        )
    await _notify(
        sessions,
        bot,
        document.user_id,
        _profile_summary(profile),
        reply_markup=profile_review_keyboard(str(profile.id)),
    )
    return "profile_draft"


async def _finish_parse_run(
    sessions: async_sessionmaker[AsyncSession], run_id: UUID, status: str, error_code: str
) -> None:
    async with sessions.begin() as session:
        await session.execute(
            update(ResumeParseRun)
            .where(ResumeParseRun.id == run_id)
            .values(status=status, error_code=error_code, completed_at=datetime.now(UTC))
        )


def _profile_summary(profile: Any) -> str:
    roles = ", ".join(profile.desired_roles) or "не указаны"
    skills = ", ".join(item.get("name", "") for item in profile.skills[:12]) or "не указаны"
    return (
        "<b>Проверьте распознанный профиль</b>\n\n"
        f"Имя: {escape(profile.full_name or 'не указано')}\n"
        f"Текущая должность: {escape(profile.current_title or 'не указана')}\n"
        f"Желаемые роли: {escape(roles)}\n"
        f"Навыки: {escape(skills)}\n\n"
        "AI может ошибаться — подтвердите или исправьте данные."
    )


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
    sessions: async_sessionmaker[AsyncSession],
    bot: Bot | None,
    user_id: UUID,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if bot is None:
        return
    async with sessions() as session:
        telegram_user_id = await session.scalar(
            select(TelegramAccount.telegram_user_id).where(TelegramAccount.user_id == user_id)
        )
    if telegram_user_id is not None:
        try:
            await bot.send_message(telegram_user_id, text, reply_markup=reply_markup)
        except Exception as exc:
            logger.warning("resume_notification_failed", error_type=type(exc).__name__)

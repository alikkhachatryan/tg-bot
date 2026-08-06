from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from docx import Document
from sqlalchemy import select

from app.ai.fake import FakeAIProvider
from app.core.config import Settings
from app.db.models.profile import CandidateProfile, ResumeParseRun
from app.db.models.resume import ResumeDocument
from app.db.models.telegram import TelegramAccount, User
from app.services.queue import RESUME_QUEUE_NAME, SCHEDULER_QUEUE_NAME, ArqResumeQueue
from app.services.resume_extraction import ResumeTextMissingError, extract_resume_text
from app.services.resumes import DOCX_MEDIA_TYPE, ResumeService, ResumeUpload, ResumeValidationError
from app.services.storage import LocalPrivateStorage
from app.workers.tasks import process_resume


def docx_bytes(text: str = "Experienced Python developer with FastAPI and PostgreSQL") -> bytes:
    stream = BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(stream)
    return stream.getvalue()


class MemoryStorage:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, media_type: str) -> None:
        del media_type
        self.data[key] = data

    async def get(self, key: str) -> bytes:
        return self.data[key]

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)


def upload(data: bytes, *, filename: str = "resume.docx") -> ResumeUpload:
    return ResumeUpload(
        telegram_file_id="telegram-file",
        filename=filename,
        declared_media_type=DOCX_MEDIA_TYPE,
        declared_size=len(data),
        data=data,
    )


def test_extract_docx_text_and_reject_empty_document() -> None:
    assert "Python developer" in extract_resume_text(docx_bytes(), DOCX_MEDIA_TYPE)
    with pytest.raises(ResumeTextMissingError):
        extract_resume_text(docx_bytes("short"), DOCX_MEDIA_TYPE)


def test_resume_validation_rejects_spoofed_and_oversized_files(sqlite_sessions) -> None:
    service = ResumeService(
        sqlite_sessions,
        MemoryStorage(),
        Settings(_env_file=None, max_resume_size_mb=1),
    )
    with pytest.raises(ResumeValidationError, match="unsupported_type"):
        service.validate(upload(b"not a PDF", filename="resume.exe"))
    with pytest.raises(ResumeValidationError, match="invalid_size"):
        service.validate(upload(b"x" * (1024 * 1024 + 1)))


async def test_local_private_storage_blocks_path_escape(tmp_path) -> None:
    storage = LocalPrivateStorage(tmp_path)
    await storage.put("safe/resume.pdf", b"data", "application/pdf")
    assert await storage.get("safe/resume.pdf") == b"data"
    with pytest.raises(ValueError, match="Invalid storage key"):
        await storage.put("../escape", b"data", "application/pdf")
    await storage.delete("safe/resume.pdf")


async def test_save_and_process_resume(sqlite_sessions) -> None:
    storage = MemoryStorage()
    settings = Settings(_env_file=None)
    service = ResumeService(sqlite_sessions, storage, settings)
    user_id = uuid4()
    async with sqlite_sessions.begin() as session:
        session.add(User(id=user_id, status="active"))
        session.add(
            TelegramAccount(
                user_id=user_id,
                telegram_user_id=123,
                username=None,
                first_name=None,
                last_name=None,
            )
        )

    resume_id = await service.save(user_id, upload(docx_bytes()))
    await service.mark_queued(resume_id)
    bot = SimpleNamespace(send_message=AsyncMock())
    result = await process_resume(
        {
            "sessions": sqlite_sessions,
            "storage": storage,
            "bot": bot,
            "ai_provider": FakeAIProvider(),
        },
        str(resume_id),
    )

    assert result == "processed"
    async with sqlite_sessions() as session:
        document = await session.scalar(
            select(ResumeDocument).where(ResumeDocument.id == resume_id)
        )
    assert document is not None
    assert document.status == "processed"
    assert "FastAPI" in (document.extracted_text or "")
    async with sqlite_sessions() as session:
        profile = await session.scalar(
            select(CandidateProfile).where(CandidateProfile.resume_id == resume_id)
        )
        parse_run = await session.scalar(
            select(ResumeParseRun).where(ResumeParseRun.resume_id == resume_id)
        )
    assert profile is not None
    assert profile.status == "draft"
    assert parse_run is not None
    assert parse_run.status == "completed"
    bot.send_message.assert_awaited_once()
    assert (
        await process_resume(
            {"sessions": sqlite_sessions, "storage": storage, "bot": bot}, str(resume_id)
        )
        == "skipped"
    )


async def test_resume_without_text_is_marked_failed(sqlite_sessions) -> None:
    storage = MemoryStorage()
    service = ResumeService(sqlite_sessions, storage, Settings(_env_file=None))
    user_id = uuid4()
    async with sqlite_sessions.begin() as session:
        session.add(User(id=user_id, status="active"))
    resume_id = await service.save(user_id, upload(docx_bytes("short")))
    await service.mark_queued(resume_id)

    assert (
        await process_resume(
            {"sessions": sqlite_sessions, "storage": storage, "bot": None}, str(resume_id)
        )
        == "text_layer_missing"
    )
    async with sqlite_sessions() as session:
        document = await session.get(ResumeDocument, resume_id)
    assert document is not None
    assert document.status == "failed"
    assert document.error_code == "text_layer_missing"


async def test_arq_queue_is_lazy_and_reuses_pool(monkeypatch) -> None:
    job = object()
    redis = SimpleNamespace(enqueue_job=AsyncMock(return_value=job), aclose=AsyncMock())
    create_pool = AsyncMock(return_value=redis)
    monkeypatch.setattr("app.services.queue.create_pool", create_pool)
    queue = ArqResumeQueue("redis://localhost:6379/0")

    first = uuid4()
    await queue.enqueue(first)
    await queue.enqueue(uuid4())
    await queue.close()

    create_pool.assert_awaited_once()
    redis.enqueue_job.assert_any_await(
        "process_resume",
        str(first),
        _job_id=str(first),
        _queue_name=RESUME_QUEUE_NAME,
    )
    redis.aclose.assert_awaited_once()


def test_resume_and_scheduler_queues_are_isolated() -> None:
    assert RESUME_QUEUE_NAME != SCHEDULER_QUEUE_NAME

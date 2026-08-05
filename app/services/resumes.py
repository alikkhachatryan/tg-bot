import hashlib
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models.resume import ResumeDocument
from app.services.storage import PrivateStorage

PDF_MEDIA_TYPE = "application/pdf"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ALLOWED_TYPES = {".pdf": PDF_MEDIA_TYPE, ".docx": DOCX_MEDIA_TYPE}


class ResumeValidationError(Exception):
    """An uploaded file does not satisfy resume security rules."""


@dataclass(frozen=True, slots=True)
class ResumeUpload:
    telegram_file_id: str
    filename: str
    declared_media_type: str | None
    declared_size: int | None
    data: bytes


class ResumeService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        storage: PrivateStorage,
        settings: Settings,
    ) -> None:
        self._sessions = sessions
        self._storage = storage
        self._max_bytes = settings.max_resume_size_mb * 1024 * 1024

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def validate(self, upload: ResumeUpload) -> str:
        if not upload.data or len(upload.data) > self._max_bytes:
            raise ResumeValidationError("invalid_size")
        if upload.declared_size is not None and upload.declared_size != len(upload.data):
            raise ResumeValidationError("size_mismatch")
        suffix = Path(upload.filename).suffix.lower()
        media_type = ALLOWED_TYPES.get(suffix)
        if media_type is None or upload.declared_media_type != media_type:
            raise ResumeValidationError("unsupported_type")
        if media_type == PDF_MEDIA_TYPE and not upload.data.startswith(b"%PDF-"):
            raise ResumeValidationError("invalid_pdf")
        if media_type == DOCX_MEDIA_TYPE:
            self._validate_docx(upload.data)
        return media_type

    @staticmethod
    def _validate_docx(data: bytes) -> None:
        try:
            with ZipFile(BytesIO(data)) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise ResumeValidationError("invalid_docx")
                if sum(item.file_size for item in archive.infolist()) > 50 * 1024 * 1024:
                    raise ResumeValidationError("unsafe_docx")
        except BadZipFile as exc:
            raise ResumeValidationError("invalid_docx") from exc

    async def save(self, user_id: UUID, upload: ResumeUpload) -> UUID:
        media_type = self.validate(upload)
        resume_id = uuid4()
        suffix = Path(upload.filename).suffix.lower()
        storage_key = f"resumes/{user_id}/{resume_id}{suffix}"
        safe_name = re.sub(r"[^\w.() -]", "_", Path(upload.filename).name)[:255]
        await self._storage.put(storage_key, upload.data, media_type)
        try:
            async with self._sessions.begin() as session:
                session.add(
                    ResumeDocument(
                        id=resume_id,
                        user_id=user_id,
                        telegram_file_id=upload.telegram_file_id,
                        original_filename=safe_name or f"resume{suffix}",
                        storage_key=storage_key,
                        media_type=media_type,
                        size_bytes=len(upload.data),
                        sha256=hashlib.sha256(upload.data).hexdigest(),
                        status="uploaded",
                    )
                )
        except Exception:
            await self._storage.delete(storage_key)
            raise
        return resume_id

    async def mark_queued(self, resume_id: UUID) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(ResumeDocument)
                .where(ResumeDocument.id == resume_id, ResumeDocument.status == "uploaded")
                .values(status="queued")
            )

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.submission import VacancySubmission
from app.db.models.telegram import ConversationState
from app.services.vacancy_text import parse_vacancy_text


class VacancySubmissionError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    submission: VacancySubmission
    duplicate: bool = False


class VacancySubmissionService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def begin(self, user_id: UUID) -> None:
        async with self._sessions.begin() as session:
            await session.merge(ConversationState(user_id=user_id, state="adding_vacancy", data={}))

    async def is_awaiting_text(self, user_id: UUID) -> bool:
        async with self._sessions() as session:
            state = await session.get(ConversationState, user_id)
            return state is not None and state.state == "adding_vacancy"

    async def submit(
        self,
        user_id: UUID,
        text: str,
        *,
        input_type: str,
        source_url: str | None = None,
    ) -> SubmissionResult:
        if input_type not in {"manual", "forwarded"}:
            raise VacancySubmissionError("invalid_input_type")
        if len(text) > 100_000:
            raise VacancySubmissionError("too_large")
        parsed = parse_vacancy_text(text)
        if parsed is None:
            raise VacancySubmissionError("not_a_vacancy")
        normalized = parsed.normalized_text
        content_hash = hashlib.sha256(normalized.casefold().encode()).hexdigest()
        async with self._sessions() as session:
            existing = await session.scalar(
                select(VacancySubmission).where(
                    VacancySubmission.user_id == user_id,
                    VacancySubmission.content_hash == content_hash,
                )
            )
        if existing is not None:
            return SubmissionResult(existing, duplicate=True)

        submission = VacancySubmission(
            user_id=user_id,
            input_type=input_type,
            status="awaiting_confirmation",
            title=parsed.title,
            company=parsed.company,
            location=parsed.location,
            workplace_type=parsed.workplace_type,
            source_url=source_url or parsed.first_url,
            normalized_text=normalized,
            content_hash=content_hash,
        )
        try:
            async with self._sessions.begin() as session:
                session.add(submission)
                await session.flush()
                await session.merge(
                    ConversationState(
                        user_id=user_id,
                        state="reviewing_vacancy",
                        data={"submission_id": str(submission.id)},
                    )
                )
        except IntegrityError:
            async with self._sessions() as session:
                existing = await session.scalar(
                    select(VacancySubmission).where(
                        VacancySubmission.user_id == user_id,
                        VacancySubmission.content_hash == content_hash,
                    )
                )
            if existing is None:
                raise
            return SubmissionResult(existing, duplicate=True)
        return SubmissionResult(submission)

    async def confirm_private(self, user_id: UUID, submission_id: UUID, keep: bool) -> bool:
        async with self._sessions.begin() as session:
            submission = await session.scalar(
                select(VacancySubmission).where(
                    VacancySubmission.id == submission_id,
                    VacancySubmission.user_id == user_id,
                    VacancySubmission.status == "awaiting_confirmation",
                )
            )
            if submission is None:
                return False
            if keep:
                submission.status = "private"
            else:
                await session.delete(submission)
            await session.execute(
                update(ConversationState)
                .where(ConversationState.user_id == user_id)
                .values(state="main_menu", data={})
            )
            return True

    async def latest_private(self, user_id: UUID, limit: int = 10) -> list[VacancySubmission]:
        async with self._sessions() as session:
            return list(
                await session.scalars(
                    select(VacancySubmission)
                    .where(
                        VacancySubmission.user_id == user_id,
                        VacancySubmission.status == "private",
                    )
                    .order_by(VacancySubmission.created_at.desc())
                    .limit(limit)
                )
            )

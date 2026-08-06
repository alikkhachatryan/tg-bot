from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.submission import VacancySubmission
from app.db.models.telegram import ConversationState, User
from app.services.submissions import VacancySubmissionError, VacancySubmissionService

VACANCY_TEXT = """Vacancy: Senior Python Developer
Company: Example Armenia
Location: Yerevan, Armenia
We are hiring a backend engineer. Requirements: Python, FastAPI, PostgreSQL.
Remote work is available. https://example.com/jobs/python
"""


async def test_private_submission_is_normalized_deduplicated_and_confirmed(
    sqlite_sessions,
) -> None:
    user_id = uuid4()
    async with sqlite_sessions.begin() as session:
        session.add(User(id=user_id, status="active"))

    service = VacancySubmissionService(sqlite_sessions)
    await service.begin(user_id)
    assert await service.is_awaiting_text(user_id)

    result = await service.submit(user_id, VACANCY_TEXT, input_type="manual")

    assert not result.duplicate
    assert result.submission.title == "Senior Python Developer"
    assert result.submission.company == "Example Armenia"
    assert result.submission.location == "Yerevan, Armenia"
    assert result.submission.workplace_type == "remote"
    assert result.submission.source_url == "https://example.com/jobs/python"
    duplicate = await service.submit(user_id, VACANCY_TEXT, input_type="forwarded")
    assert duplicate.duplicate
    assert duplicate.submission.id == result.submission.id

    assert await service.confirm_private(user_id, result.submission.id, keep=True)
    assert not await service.confirm_private(user_id, result.submission.id, keep=True)
    async with sqlite_sessions() as session:
        stored = await session.get(VacancySubmission, result.submission.id)
        state = await session.get(ConversationState, user_id)
    assert stored is not None and stored.status == "private"
    assert state is not None and state.state == "main_menu"
    private_items = await service.latest_private(user_id)
    assert [item.id for item in private_items] == [result.submission.id]


async def test_discard_removes_submission_and_invalid_text_is_rejected(sqlite_sessions) -> None:
    user_id = uuid4()
    async with sqlite_sessions.begin() as session:
        session.add(User(id=user_id, status="active"))
    service = VacancySubmissionService(sqlite_sessions)

    with pytest.raises(VacancySubmissionError, match="not_a_vacancy"):
        await service.submit(user_id, "Привет, как дела?", input_type="manual")

    result = await service.submit(
        user_id,
        VACANCY_TEXT.replace("Senior Python Developer", "Middle Python Developer"),
        input_type="forwarded",
    )
    assert await service.confirm_private(user_id, result.submission.id, keep=False)
    async with sqlite_sessions() as session:
        stored = await session.scalar(
            select(VacancySubmission).where(VacancySubmission.id == result.submission.id)
        )
    assert stored is None

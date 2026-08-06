from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models.matching import VacancyMatch
from app.db.models.onboarding import SearchPreference
from app.db.models.profile import CandidateProfile
from app.db.models.resume import ResumeDocument
from app.db.models.telegram import User
from app.db.models.vacancy import Vacancy
from app.services.matching import MatchingService, MatchingUnavailableError, calculate_match


def profile(**changes: Any) -> CandidateProfile:
    values = {
        "id": uuid4(),
        "user_id": uuid4(),
        "resume_id": uuid4(),
        "status": "confirmed",
        "current_title": "Python Developer",
        "desired_roles": ["Backend Developer"],
        "total_experience_months": 60,
        "skills": [{"name": "Python"}, {"name": "FastAPI"}],
        "languages": [{"name": "English", "level": "B2"}],
    }
    values.update(changes)
    return CandidateProfile(**values)


def preference(**changes: Any) -> SearchPreference:
    values = {
        "user_id": uuid4(),
        "desired_roles": ["Backend Developer"],
        "preferred_locations": ["Armenia", "Yerevan"],
        "work_modes": ["remote", "hybrid"],
        "allow_international_remote": True,
        "willing_to_relocate": False,
        "relocation_locations": [],
        "min_salary": 2000,
        "salary_currency": "USD",
        "languages": ["English"],
        "status": "active",
    }
    values.update(changes)
    return SearchPreference(**values)


def vacancy(**changes: Any) -> Vacancy:
    values = {
        "id": uuid4(),
        "fingerprint": "a" * 64,
        "title": "Senior Python Developer",
        "company": "Armenian Tech",
        "description": "3+ years. Python, FastAPI and Docker. English is required.",
        "location": "Yerevan, Armenia",
        "country_code": "AM",
        "workplace_type": "hybrid",
        "salary_min": 2500,
        "salary_max": 3500,
        "salary_currency": "USD",
        "canonical_url": "https://example.com/job",
    }
    values.update(changes)
    return Vacancy(**values)


def test_explainable_match_scores_profile_components() -> None:
    result = calculate_match(
        profile(),
        preference(),
        vacancy(),
        Settings(_env_file=None).matching_weights,
    )

    assert result.eligible is True
    assert result.score >= 80
    assert result.components == {
        "skills": 67,
        "experience": 100,
        "role": 100,
        "location": 100,
        "language": 100,
        "salary": 100,
    }
    assert any("Python" in reason for reason in result.explanations)
    assert any("docker" in reason.casefold() for reason in result.explanations)


@pytest.mark.parametrize(
    ("job", "expected_reason"),
    [
        (
            vacancy(
                workplace_type="office",
                location="Berlin, Germany",
                country_code="DE",
            ),
            "Формат работы",
        ),
        (
            vacancy(
                workplace_type="remote",
                location="Remote",
                country_code=None,
                remote_scope="US only",
            ),
            "недоступна из Армении",
        ),
        (vacancy(salary_min=1000, salary_max=1500), "зарплата ниже"),
        (vacancy(expires_at=datetime.now(UTC) - timedelta(days=1)), "истекла"),
    ],
)
def test_hard_filters_exclude_incompatible_vacancies(job: Vacancy, expected_reason: str) -> None:
    result = calculate_match(
        profile(),
        preference(),
        job,
        Settings(_env_file=None).matching_weights,
    )

    assert result.eligible is False
    assert any(expected_reason in reason for reason in result.filter_reasons)


async def test_service_persists_ranks_and_does_not_repeat_matches(
    sqlite_sessions: Any,
) -> None:
    async with sqlite_sessions.begin() as session:
        user = User(status="active")
        session.add(user)
        await session.flush()
        resume = ResumeDocument(
            user_id=user.id,
            telegram_file_id="file",
            original_filename="cv.pdf",
            storage_key=f"resumes/{user.id}/cv.pdf",
            media_type="application/pdf",
            size_bytes=100,
            sha256="b" * 64,
            status="processed",
        )
        session.add(resume)
        await session.flush()
        session.add(
            profile(
                id=uuid4(),
                user_id=user.id,
                resume_id=resume.id,
                confirmed_at=datetime.now(UTC),
            )
        )
        session.add(preference(user_id=user.id))
        session.add(vacancy())
        user_id = user.id

    service = MatchingService(sqlite_sessions, Settings(_env_file=None))
    first = await service.new_matches(user_id)
    second = await service.new_matches(user_id)

    assert len(first) == 1
    assert first[0].match.score >= 80
    assert second == []
    async with sqlite_sessions() as session:
        count = await session.scalar(select(func.count()).select_from(VacancyMatch))
        stored = await session.scalar(select(VacancyMatch))
    assert count == 1
    assert stored is not None and stored.presented_at is not None


async def test_service_requires_confirmed_profile_and_preferences(sqlite_sessions: Any) -> None:
    async with sqlite_sessions.begin() as session:
        user = User(status="active")
        session.add(user)
        await session.flush()
        user_id = user.id

    service = MatchingService(sqlite_sessions, Settings(_env_file=None))
    with pytest.raises(MatchingUnavailableError, match="profile_missing"):
        await service.new_matches(user_id)

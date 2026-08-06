from uuid import uuid4

import pytest

from app.db.models.onboarding import SearchPreference
from app.db.models.profile import CandidateProfile
from app.db.models.resume import ResumeDocument
from app.db.models.telegram import User
from app.services.onboarding import OnboardingService, OnboardingValidationError


async def test_onboarding_branches_persists_and_resumes(sqlite_sessions) -> None:
    user_id = uuid4()
    async with sqlite_sessions.begin() as session:
        session.add(User(id=user_id, status="active"))

    service = OnboardingService(sqlite_sessions)
    step = await service.start(user_id)
    assert step.question is not None
    assert step.question.key == "desired_roles"

    step = await service.answer(user_id, "Python Developer, Backend Developer")
    assert step is not None and step.question is not None
    assert step.question.key == "preferred_locations"

    resumed = await service.current(user_id)
    assert resumed is not None and resumed.question is not None
    assert resumed.question.key == "preferred_locations"

    await service.answer(user_id, "Армения, Ереван")
    await service.answer(user_id, "any")
    await service.answer(user_id, "yes")
    step = await service.answer(user_id, "no")
    assert step is not None and step.question is not None
    assert step.question.key == "min_salary"

    step = await service.skip(user_id)
    assert step is not None and step.question is not None
    assert step.question.key == "languages"
    completed = await service.answer(user_id, "Армянский, Английский, Русский")
    assert completed is not None and completed.completed

    async with sqlite_sessions() as session:
        preferences = await session.get(SearchPreference, user_id)
    assert preferences is not None
    assert preferences.preferred_locations == ["Армения", "Ереван"]
    assert preferences.allow_international_remote is True
    assert preferences.willing_to_relocate is False
    assert preferences.relocation_locations == []
    assert preferences.min_salary is None


async def test_onboarding_reuses_roles_and_languages_from_confirmed_profile(
    sqlite_sessions,
) -> None:
    user_id = uuid4()
    resume_id = uuid4()
    async with sqlite_sessions.begin() as session:
        session.add(User(id=user_id, status="active"))

    service = OnboardingService(sqlite_sessions)
    initial = await service.start(user_id)
    assert initial.question is not None and initial.question.key == "desired_roles"

    async with sqlite_sessions.begin() as session:
        session.add(
            ResumeDocument(
                id=resume_id,
                user_id=user_id,
                telegram_file_id="file",
                original_filename="resume.pdf",
                storage_key=f"resumes/{user_id}/{resume_id}.pdf",
                media_type="application/pdf",
                size_bytes=100,
                sha256="b" * 64,
                status="processed",
            )
        )
        session.add(
            CandidateProfile(
                user_id=user_id,
                resume_id=resume_id,
                status="confirmed",
                desired_roles=["Backend Developer", "Python Developer"],
                languages=[
                    {"name": "Armenian", "level": "native"},
                    {"name": "English", "level": "B2"},
                ],
            )
        )

    resumed = await service.start(user_id)

    assert resumed.question is not None
    assert resumed.question.key == "preferred_locations"
    assert resumed.can_go_back

    await service.answer(user_id, "Армения")
    await service.answer(user_id, "any")
    await service.answer(user_id, "yes")
    await service.answer(user_id, "no")
    completed = await service.skip(user_id)
    assert completed is not None and completed.completed
    async with sqlite_sessions() as session:
        preferences = await session.get(SearchPreference, user_id)
    assert preferences is not None
    assert preferences.languages == ["Armenian", "English"]


async def test_onboarding_back_rewinds_last_answer(sqlite_sessions) -> None:
    user_id = uuid4()
    async with sqlite_sessions.begin() as session:
        session.add(User(id=user_id, status="active"))
    service = OnboardingService(sqlite_sessions)
    await service.start(user_id)
    await service.answer(user_id, "Backend Developer")

    step = await service.back(user_id)

    assert step is not None and step.question is not None
    assert step.question.key == "desired_roles"
    assert not step.can_go_back


async def test_onboarding_relocation_salary_and_stale_button(sqlite_sessions) -> None:
    user_id = uuid4()
    async with sqlite_sessions.begin() as session:
        session.add(User(id=user_id, status="active"))
    service = OnboardingService(sqlite_sessions)
    await service.start(user_id)
    await service.answer(user_id, "Backend Developer")
    await service.answer(user_id, "Армения")
    await service.answer(user_id, "remote")
    await service.answer(user_id, "yes")
    step = await service.answer(user_id, "yes")
    assert step is not None and step.question is not None
    assert step.question.key == "relocation_locations"
    await service.answer(user_id, "Грузия, Германия")
    with pytest.raises(OnboardingValidationError, match="целое число"):
        await service.answer(user_id, "две тысячи")
    await service.answer(user_id, "2000")

    stale = await service.answer(user_id, "USD", expected_key="min_salary")
    assert stale is not None and stale.question is not None
    assert stale.question.key == "salary_currency"
    await service.answer(user_id, "USD", expected_key="salary_currency")
    completed = await service.skip(user_id)
    assert completed is not None and completed.completed


async def test_onboarding_work_modes_support_multiple_selection(sqlite_sessions) -> None:
    user_id = uuid4()
    async with sqlite_sessions.begin() as session:
        session.add(User(id=user_id, status="active"))
    service = OnboardingService(sqlite_sessions)
    await service.start(user_id)
    await service.answer(user_id, "Backend Developer")
    await service.answer(user_id, "Армения")

    step = await service.toggle_work_mode(user_id, "remote")
    assert step is not None and step.selected_values == ("remote",)
    step = await service.toggle_work_mode(user_id, "hybrid")
    assert step is not None and step.selected_values == ("remote", "hybrid")
    step = await service.toggle_work_mode(user_id, "remote")
    assert step is not None and step.selected_values == ("hybrid",)

    advanced = await service.submit_work_modes(user_id)
    assert advanced is not None and advanced.question is not None
    assert advanced.question.key == "allow_international_remote"


async def test_onboarding_requires_a_work_mode_selection(sqlite_sessions) -> None:
    user_id = uuid4()
    async with sqlite_sessions.begin() as session:
        session.add(User(id=user_id, status="active"))
    service = OnboardingService(sqlite_sessions)
    await service.start(user_id)
    await service.answer(user_id, "Backend Developer")
    await service.answer(user_id, "Армения")

    with pytest.raises(OnboardingValidationError, match="хотя бы один"):
        await service.submit_work_modes(user_id)

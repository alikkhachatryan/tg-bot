from uuid import uuid4

from sqlalchemy import select

from app.ai.schemas import CandidateProfileData, SkillData
from app.db.models.profile import CandidateProfile
from app.db.models.resume import ResumeDocument
from app.db.models.telegram import ConversationState, User
from app.services.profiles import ProfileService


async def test_profile_draft_edit_and_confirmation(sqlite_sessions) -> None:
    user_id = uuid4()
    resume_id = uuid4()
    async with sqlite_sessions.begin() as session:
        session.add(User(id=user_id, status="active"))
        session.add(ConversationState(user_id=user_id, state="awaiting_resume", data={}))
        session.add(
            ResumeDocument(
                id=resume_id,
                user_id=user_id,
                telegram_file_id="file",
                original_filename="resume.pdf",
                storage_key=f"resumes/{user_id}/{resume_id}.pdf",
                media_type="application/pdf",
                size_bytes=100,
                sha256="a" * 64,
                status="processed",
            )
        )

    service = ProfileService(sqlite_sessions)
    profile = await service.save_draft(
        user_id,
        resume_id,
        CandidateProfileData(
            full_name="Demo User",
            current_title="Developer",
            skills=[SkillData(name="Python")],
        ),
    )
    assert profile.status == "draft"
    assert not await service.begin_edit(uuid4(), profile.id, "desired_roles")
    assert not await service.begin_edit(user_id, profile.id, "unknown")
    assert await service.begin_edit(user_id, profile.id, "desired_roles")

    edited = await service.apply_pending_edit(user_id, "Backend Developer, API Developer")
    assert edited is not None
    assert edited.desired_roles == ["Backend Developer", "API Developer"]
    assert await service.confirm(user_id, profile.id)
    assert not await service.confirm(user_id, profile.id)

    async with sqlite_sessions() as session:
        stored = await session.scalar(
            select(CandidateProfile).where(CandidateProfile.id == profile.id)
        )
    assert stored is not None
    assert stored.status == "confirmed"
    assert stored.confirmed_at is not None

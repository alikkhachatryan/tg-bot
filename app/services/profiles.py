from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.schemas import CandidateProfileData
from app.db.models.profile import CandidateProfile
from app.db.models.telegram import ConversationState

EDITABLE_FIELDS = frozenset({"full_name", "current_title", "desired_roles", "professional_summary"})


class ProfileService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save_draft(
        self, user_id: UUID, resume_id: UUID, data: CandidateProfileData
    ) -> CandidateProfile:
        values = _profile_values(data)
        async with self._sessions.begin() as session:
            profile = await session.scalar(
                select(CandidateProfile).where(CandidateProfile.resume_id == resume_id)
            )
            if profile is None:
                profile = CandidateProfile(
                    user_id=user_id,
                    resume_id=resume_id,
                    status="draft",
                    **values,
                )
                session.add(profile)
            else:
                for key, value in values.items():
                    setattr(profile, key, value)
                profile.status = "draft"
                profile.confirmed_at = None
            await session.flush()
            await session.execute(
                update(ConversationState)
                .where(ConversationState.user_id == user_id)
                .values(state="reviewing_profile", data={"profile_id": str(profile.id)})
            )
            return profile

    async def confirm(self, user_id: UUID, profile_id: UUID) -> bool:
        async with self._sessions.begin() as session:
            changed = await session.scalar(
                update(CandidateProfile)
                .where(
                    CandidateProfile.id == profile_id,
                    CandidateProfile.user_id == user_id,
                    CandidateProfile.status == "draft",
                )
                .values(status="confirmed", confirmed_at=datetime.now(UTC))
                .returning(CandidateProfile.id)
            )
            if changed is not None:
                await session.execute(
                    update(ConversationState)
                    .where(ConversationState.user_id == user_id)
                    .values(state="profile_confirmed", data={})
                )
        return changed is not None

    async def latest_confirmed(self, user_id: UUID) -> CandidateProfile | None:
        async with self._sessions() as session:
            profile: CandidateProfile | None = await session.scalar(
                select(CandidateProfile)
                .where(
                    CandidateProfile.user_id == user_id,
                    CandidateProfile.status == "confirmed",
                )
                .order_by(CandidateProfile.confirmed_at.desc())
                .limit(1)
            )
            return profile

    async def begin_edit(self, user_id: UUID, profile_id: UUID, field: str) -> bool:
        if field not in EDITABLE_FIELDS:
            return False
        async with self._sessions.begin() as session:
            owned = await session.scalar(
                select(CandidateProfile.id).where(
                    CandidateProfile.id == profile_id,
                    CandidateProfile.user_id == user_id,
                    CandidateProfile.status == "draft",
                )
            )
            if owned is None:
                return False
            await session.execute(
                update(ConversationState)
                .where(ConversationState.user_id == user_id)
                .values(
                    state=f"editing_profile:{field}",
                    data={"profile_id": str(profile_id)},
                )
            )
        return True

    async def apply_pending_edit(self, user_id: UUID, text: str) -> CandidateProfile | None:
        value = text.strip()
        if not value:
            return None
        async with self._sessions.begin() as session:
            state = await session.get(ConversationState, user_id)
            if state is None or not state.state.startswith("editing_profile:"):
                return None
            field = state.state.removeprefix("editing_profile:")
            if field not in EDITABLE_FIELDS:
                return None
            raw_profile_id = state.data.get("profile_id")
            if not isinstance(raw_profile_id, str):
                return None
            profile = await session.scalar(
                select(CandidateProfile).where(
                    CandidateProfile.id == UUID(raw_profile_id),
                    CandidateProfile.user_id == user_id,
                    CandidateProfile.status == "draft",
                )
            )
            if profile is None:
                return None
            if field == "desired_roles":
                profile.desired_roles = [item.strip() for item in value.split(",") if item.strip()][
                    :20
                ]
            else:
                limit = 3000 if field == "professional_summary" else 255
                setattr(profile, field, value[:limit])
            state.state = "reviewing_profile"
            state.data = {"profile_id": str(profile.id)}
            return profile


def _profile_values(data: CandidateProfileData) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    return {
        "full_name": payload["full_name"],
        "current_title": payload["current_title"],
        "desired_roles": payload["desired_roles"],
        "professional_summary": payload["professional_summary"],
        "total_experience_months": payload["total_experience_months"],
        "skills": payload["skills"],
        "work_experience": payload["work_experience"],
        "projects": payload["projects"],
        "education": payload["education"],
        "languages": payload["languages"],
        "location": payload["location"],
        "contacts": payload["contacts"],
    }

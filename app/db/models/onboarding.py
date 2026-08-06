from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SearchPreference(Base):
    __tablename__ = "search_preferences"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    desired_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    preferred_locations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    work_modes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    allow_international_remote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    willing_to_relocate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    relocation_locations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    min_salary: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    languages: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OnboardingSession(Base):
    __tablename__ = "onboarding_sessions"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    current_question: Mapped[str] = mapped_column(String(64), nullable=False)
    answers: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    history: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VacancyMatch(Base):
    __tablename__ = "vacancy_matches"
    __table_args__ = (
        UniqueConstraint("user_id", "vacancy_id", name="uq_vacancy_matches_user_vacancy"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vacancy_id: Mapped[UUID] = mapped_column(
        ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    components: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    explanations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    filter_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    presented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

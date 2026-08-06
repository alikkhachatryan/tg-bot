"""Add explainable vacancy matches.

Revision ID: 20260806_0008
Revises: 20260806_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260806_0008"
down_revision: str | None = "20260806_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vacancy_matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("vacancy_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("explanations", sa.JSON(), nullable=False),
        sa.Column("filter_reasons", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("presented_at", sa.DateTime(timezone=True)),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["candidate_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vacancy_id"], ["vacancies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vacancy_matches")),
        sa.UniqueConstraint("user_id", "vacancy_id", name="uq_vacancy_matches_user_vacancy"),
    )
    op.create_index(op.f("ix_vacancy_matches_user_id"), "vacancy_matches", ["user_id"])
    op.create_index(op.f("ix_vacancy_matches_vacancy_id"), "vacancy_matches", ["vacancy_id"])
    op.create_index(op.f("ix_vacancy_matches_profile_id"), "vacancy_matches", ["profile_id"])
    op.create_index(op.f("ix_vacancy_matches_eligible"), "vacancy_matches", ["eligible"])
    op.create_index(op.f("ix_vacancy_matches_score"), "vacancy_matches", ["score"])
    op.create_index(op.f("ix_vacancy_matches_presented_at"), "vacancy_matches", ["presented_at"])


def downgrade() -> None:
    op.drop_table("vacancy_matches")

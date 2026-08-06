"""Add durable onboarding and search preferences.

Revision ID: 20260806_0005
Revises: 20260806_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260806_0005"
down_revision: str | None = "20260806_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "onboarding_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("current_question", sa.String(64), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_onboarding_sessions")),
    )
    op.create_table(
        "search_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("desired_roles", sa.JSON(), nullable=False),
        sa.Column("preferred_locations", sa.JSON(), nullable=False),
        sa.Column("work_modes", sa.JSON(), nullable=False),
        sa.Column("allow_international_remote", sa.Boolean(), nullable=False),
        sa.Column("willing_to_relocate", sa.Boolean(), nullable=False),
        sa.Column("relocation_locations", sa.JSON(), nullable=False),
        sa.Column("min_salary", sa.Integer()),
        sa.Column("salary_currency", sa.String(8)),
        sa.Column("languages", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_search_preferences")),
    )


def downgrade() -> None:
    op.drop_table("search_preferences")
    op.drop_table("onboarding_sessions")

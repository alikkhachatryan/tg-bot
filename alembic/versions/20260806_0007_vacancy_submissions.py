"""Add private user vacancy submissions.

Revision ID: 20260806_0007
Revises: 20260806_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260806_0007"
down_revision: str | None = "20260806_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vacancy_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("input_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company", sa.String(255)),
        sa.Column("location", sa.String(500)),
        sa.Column("workplace_type", sa.String(32), nullable=False),
        sa.Column("source_url", sa.String(2000)),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vacancy_submissions")),
        sa.UniqueConstraint("user_id", "content_hash", name="uq_vacancy_submissions_user_content"),
    )
    op.create_index(op.f("ix_vacancy_submissions_user_id"), "vacancy_submissions", ["user_id"])
    op.create_index(op.f("ix_vacancy_submissions_status"), "vacancy_submissions", ["status"])


def downgrade() -> None:
    op.drop_table("vacancy_submissions")

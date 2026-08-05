"""Add private resume documents and processing state.

Revision ID: 20260806_0003
Revises: 20260806_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260806_0003"
down_revision: str | None = "20260806_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resume_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("telegram_file_id", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("extracted_text", sa.Text()),
        sa.Column("error_code", sa.String(64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resume_documents")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_resume_documents_storage_key")),
    )
    op.create_index(op.f("ix_resume_documents_sha256"), "resume_documents", ["sha256"])
    op.create_index(op.f("ix_resume_documents_status"), "resume_documents", ["status"])
    op.create_index(op.f("ix_resume_documents_user_id"), "resume_documents", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_resume_documents_user_id"), table_name="resume_documents")
    op.drop_index(op.f("ix_resume_documents_status"), table_name="resume_documents")
    op.drop_index(op.f("ix_resume_documents_sha256"), table_name="resume_documents")
    op.drop_table("resume_documents")

"""Add AI parse runs and candidate profile drafts.

Revision ID: 20260806_0004
Revises: 20260806_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260806_0004"
down_revision: str | None = "20260806_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("resume_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("current_title", sa.String(255)),
        sa.Column("desired_roles", sa.JSON(), nullable=False),
        sa.Column("professional_summary", sa.Text()),
        sa.Column("total_experience_months", sa.Integer()),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("work_experience", sa.JSON(), nullable=False),
        sa.Column("projects", sa.JSON(), nullable=False),
        sa.Column("education", sa.JSON(), nullable=False),
        sa.Column("languages", sa.JSON(), nullable=False),
        sa.Column("location", sa.String(255)),
        sa.Column("contacts", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["resume_id"], ["resume_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_profiles")),
        sa.UniqueConstraint("resume_id", name="uq_candidate_profiles_resume_id"),
    )
    op.create_index(op.f("ix_candidate_profiles_status"), "candidate_profiles", ["status"])
    op.create_index(op.f("ix_candidate_profiles_user_id"), "candidate_profiles", ["user_id"])

    op.create_table(
        "resume_parse_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resume_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider_request_id", sa.String(255)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("error_code", sa.String(64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["resume_id"], ["resume_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resume_parse_runs")),
    )
    op.create_index(op.f("ix_resume_parse_runs_resume_id"), "resume_parse_runs", ["resume_id"])
    op.create_index(op.f("ix_resume_parse_runs_status"), "resume_parse_runs", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_resume_parse_runs_status"), table_name="resume_parse_runs")
    op.drop_index(op.f("ix_resume_parse_runs_resume_id"), table_name="resume_parse_runs")
    op.drop_table("resume_parse_runs")
    op.drop_index(op.f("ix_candidate_profiles_user_id"), table_name="candidate_profiles")
    op.drop_index(op.f("ix_candidate_profiles_status"), table_name="candidate_profiles")
    op.drop_table("candidate_profiles")

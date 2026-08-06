"""Add canonical vacancies and source provenance.

Revision ID: 20260806_0006
Revises: 20260806_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260806_0006"
down_revision: str | None = "20260806_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vacancies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(500)),
        sa.Column("country_code", sa.String(2)),
        sa.Column("workplace_type", sa.String(32), nullable=False),
        sa.Column("employment_type", sa.String(64)),
        sa.Column("remote_scope", sa.String(255)),
        sa.Column("salary_min", sa.Integer()),
        sa.Column("salary_max", sa.Integer()),
        sa.Column("salary_currency", sa.String(8)),
        sa.Column("canonical_url", sa.String(2000), nullable=False),
        sa.Column("apply_url", sa.String(2000)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vacancies")),
        sa.UniqueConstraint("fingerprint", name="uq_vacancies_fingerprint"),
    )
    op.create_index(op.f("ix_vacancies_title"), "vacancies", ["title"])
    op.create_index(op.f("ix_vacancies_company"), "vacancies", ["company"])
    op.create_index(op.f("ix_vacancies_location"), "vacancies", ["location"])
    op.create_index(op.f("ix_vacancies_country_code"), "vacancies", ["country_code"])
    op.create_index(op.f("ix_vacancies_workplace_type"), "vacancies", ["workplace_type"])
    op.create_index(op.f("ix_vacancies_published_at"), "vacancies", ["published_at"])
    op.create_index(op.f("ix_vacancies_last_seen_at"), "vacancies", ["last_seen_at"])

    op.create_table(
        "vacancy_ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("fetched_count", sa.Integer(), nullable=False),
        sa.Column("stored_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vacancy_ingestion_runs")),
    )
    op.create_index(op.f("ix_vacancy_ingestion_runs_source"), "vacancy_ingestion_runs", ["source"])
    op.create_index(op.f("ix_vacancy_ingestion_runs_status"), "vacancy_ingestion_runs", ["status"])

    op.create_table(
        "vacancy_origins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vacancy_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("attribution", sa.String(255)),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["vacancy_id"], ["vacancies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vacancy_origins")),
        sa.UniqueConstraint("source", "external_id", name="uq_vacancy_origins_source_external_id"),
    )
    op.create_index(op.f("ix_vacancy_origins_vacancy_id"), "vacancy_origins", ["vacancy_id"])
    op.create_index(op.f("ix_vacancy_origins_source"), "vacancy_origins", ["source"])


def downgrade() -> None:
    op.drop_table("vacancy_origins")
    op.drop_table("vacancy_ingestion_runs")
    op.drop_table("vacancies")

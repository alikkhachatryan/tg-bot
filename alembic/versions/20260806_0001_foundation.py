"""Establish the migration baseline.

Revision ID: 20260806_0001
Revises:
Create Date: 2026-08-06
"""

from collections.abc import Sequence

revision: str = "20260806_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Domain tables are introduced with their owning implementation stages."""


def downgrade() -> None:
    """The baseline migration has no schema objects to remove."""

"""Initial empty migration (no data model yet)

Revision ID: 0001
Revises:
Create Date: 2026-11-26
"""

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Intentionally empty. The data model follows in the next issue."""


def downgrade() -> None:
    """Nothing to undo."""

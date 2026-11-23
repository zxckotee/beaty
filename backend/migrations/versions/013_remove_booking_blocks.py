"""Remove manager booking blocks (schedule_exception kind=block).

Revision ID: 013
Revises: 012
"""

from collections.abc import Sequence

from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM schedule_exception WHERE kind = 'block'")


def downgrade() -> None:
    pass
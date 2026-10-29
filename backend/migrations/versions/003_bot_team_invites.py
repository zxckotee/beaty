"""Staff profile fields and staff_invite for bot-only team onboarding

Revision ID: 003
Revises: 002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("staff_member", sa.Column("bio", sa.Text(), nullable=True))
    op.add_column("staff_member", sa.Column("specialization", sa.String(512), nullable=True))
    op.add_column("staff_member", sa.Column("photo_file_id", sa.String(256), nullable=True))

    op.create_table(
        "staff_invite",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "staff_member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_member.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "intended_roles",
            postgresql.JSONB(),
            nullable=False,
            server_default='["specialist"]',
        ),
        sa.Column(
            "created_by_user_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("staff_invite")
    op.drop_column("staff_member", "photo_file_id")
    op.drop_column("staff_member", "specialization")
    op.drop_column("staff_member", "bio")

"""Client–bot messenger log for manager web cabinet.

Revision ID: 010
Revises: 009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_chat_message",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("client_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("author", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("telegram_file_id", sa.String(255), nullable=True),
        sa.Column("telegram_file_unique_id", sa.String(255), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "staff_member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_member.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("meta", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_client_chat_tenant_client_created",
        "client_chat_message",
        ["tenant_id", "client_profile_id", "created_at"],
    )
    op.create_index("ix_client_chat_client", "client_chat_message", ["client_profile_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_client_chat_client", table_name="client_chat_message")
    op.drop_index("ix_client_chat_tenant_client_created", table_name="client_chat_message")
    op.drop_table("client_chat_message")
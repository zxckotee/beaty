"""Dual messenger: MAX tenant bots and multi-platform user accounts

Revision ID: 012
Revises: 011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenant", sa.Column("max_bot_id", sa.BigInteger(), nullable=True))
    op.add_column("tenant", sa.Column("max_bot_username", sa.String(length=64), nullable=True))
    op.add_column("tenant", sa.Column("max_bot_token_encrypted", sa.Text(), nullable=True))
    op.add_column("tenant", sa.Column("max_webhook_secret", sa.String(length=64), nullable=True))
    op.add_column("tenant", sa.Column("max_bot_status", sa.String(length=32), server_default="active", nullable=False))
    op.create_index("ix_tenant_max_bot_id", "tenant", ["max_bot_id"], unique=True)

    op.add_column("user_account", sa.Column("max_user_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "user_account",
        sa.Column("messenger_prefs", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.alter_column("user_account", "telegram_user_id", existing_type=sa.BigInteger(), nullable=True)
    op.create_index("ix_user_account_max_user_id", "user_account", ["max_user_id"], unique=True)
    op.create_check_constraint(
        "ck_user_account_messenger_id",
        "user_account",
        "telegram_user_id IS NOT NULL OR max_user_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_user_account_messenger_id", "user_account", type_="check")
    op.drop_index("ix_user_account_max_user_id", table_name="user_account")
    op.drop_column("user_account", "messenger_prefs")
    op.drop_column("user_account", "max_user_id")
    op.alter_column("user_account", "telegram_user_id", existing_type=sa.BigInteger(), nullable=False)

    op.drop_index("ix_tenant_max_bot_id", table_name="tenant")
    op.drop_column("tenant", "max_bot_status")
    op.drop_column("tenant", "max_webhook_secret")
    op.drop_column("tenant", "max_bot_token_encrypted")
    op.drop_column("tenant", "max_bot_username")
    op.drop_column("tenant", "max_bot_id")
"""Apply dual-messenger schema if a stale revision 012 skipped it.

If production alembic stamped 012 from the short-lived 012_remove_booking_blocks
revision (parallel branch), dual messenger columns were never added while app code
expects them. This migration is idempotent and safe to run after 013.

Revision ID: 014
Revises: 013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def _index_names(table: str) -> set[str]:
    bind = op.get_bind()
    return {i["name"] for i in inspect(bind).get_indexes(table)}


def _constraint_names(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_check_constraints(table)}


def upgrade() -> None:
    tenant_cols = _table_columns("tenant")
    if "max_bot_id" not in tenant_cols:
        op.add_column("tenant", sa.Column("max_bot_id", sa.BigInteger(), nullable=True))
    if "max_bot_username" not in tenant_cols:
        op.add_column("tenant", sa.Column("max_bot_username", sa.String(length=64), nullable=True))
    if "max_bot_token_encrypted" not in tenant_cols:
        op.add_column("tenant", sa.Column("max_bot_token_encrypted", sa.Text(), nullable=True))
    if "max_webhook_secret" not in tenant_cols:
        op.add_column("tenant", sa.Column("max_webhook_secret", sa.String(length=64), nullable=True))
    if "max_bot_status" not in tenant_cols:
        op.add_column(
            "tenant",
            sa.Column("max_bot_status", sa.String(length=32), server_default="active", nullable=False),
        )
    if "ix_tenant_max_bot_id" not in _index_names("tenant"):
        op.create_index("ix_tenant_max_bot_id", "tenant", ["max_bot_id"], unique=True)

    user_cols = _table_columns("user_account")
    if "max_user_id" not in user_cols:
        op.add_column("user_account", sa.Column("max_user_id", sa.BigInteger(), nullable=True))
    if "messenger_prefs" not in user_cols:
        op.add_column(
            "user_account",
            sa.Column(
                "messenger_prefs",
                postgresql.JSONB(),
                server_default=sa.text("'{}'::jsonb"),
                nullable=False,
            ),
        )
    if "telegram_user_id" in user_cols:
        op.alter_column("user_account", "telegram_user_id", existing_type=sa.BigInteger(), nullable=True)
    if "ix_user_account_max_user_id" not in _index_names("user_account"):
        op.create_index("ix_user_account_max_user_id", "user_account", ["max_user_id"], unique=True)
    if "ck_user_account_messenger_id" not in _constraint_names("user_account"):
        op.create_check_constraint(
            "ck_user_account_messenger_id",
            "user_account",
            "telegram_user_id IS NOT NULL OR max_user_id IS NOT NULL",
        )


def downgrade() -> None:
    pass
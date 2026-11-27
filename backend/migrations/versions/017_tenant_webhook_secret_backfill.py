"""Backfill tenant.webhook_secret where missing."""

from __future__ import annotations

import secrets

import sqlalchemy as sa
from alembic import op

revision = "017_tenant_webhook_secret"
down_revision = "016_dgis_locations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id FROM tenant WHERE webhook_secret IS NULL OR trim(webhook_secret) = ''"
        )
    ).fetchall()
    for (tenant_id,) in rows:
        secret = secrets.token_hex(16)
        conn.execute(
            sa.text("UPDATE tenant SET webhook_secret = :secret WHERE id = :id"),
            {"secret": secret, "id": tenant_id},
        )


def downgrade() -> None:
    pass
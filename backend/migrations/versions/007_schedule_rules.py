"""Reusable schedule rules (shift patterns) per tenant.

Revision ID: 007
Revises: 006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedule_rule",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("start_time", sa.String(8), nullable=False),
        sa.Column("end_time", sa.String(8), nullable=False),
        sa.Column("break_start", sa.String(8), nullable=True),
        sa.Column("break_end", sa.String(8), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_schedule_rule_tenant", "schedule_rule", ["tenant_id"])
    op.create_index(
        "uq_schedule_rule_tenant_name",
        "schedule_rule",
        ["tenant_id", sa.text("lower(trim(name))")],
        unique=True,
    )
    op.add_column(
        "schedule_template",
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("schedule_rule.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("schedule_template", "rule_id")
    op.drop_index("uq_schedule_rule_tenant_name", table_name="schedule_rule")
    op.drop_index("ix_schedule_rule_tenant", table_name="schedule_rule")
    op.drop_table("schedule_rule")
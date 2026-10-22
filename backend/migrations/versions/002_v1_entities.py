"""v1 entities: reviews, waitlist, courses, finance, marketing

Revision ID: 002
Revises: 001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = [
    "resource",
    "waitlist_entry",
    "review",
    "course_template",
    "course_enrollment",
    "payment",
    "promotion",
    "promo_code",
    "loyalty_rule",
    "payout",
    "platform_invoice",
]


def upgrade() -> None:
    op.create_table(
        "resource",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branch.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
    )
    op.create_table(
        "waitlist_entry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("service.id", ondelete="CASCADE"), nullable=False),
        sa.Column("staff_member_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("staff_member.id", ondelete="SET NULL")),
        sa.Column("preferred_date", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "review",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("booking.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("client_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("staff_rating", sa.Integer()),
        sa.Column("salon_rating", sa.Integer()),
        sa.Column("text", sa.Text()),
        sa.Column("business_reply", sa.Text()),
        sa.Column("moderation_status", sa.String(32), server_default="published"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "course_template",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sessions_count", sa.Integer(), nullable=False),
        sa.Column("min_days_between", sa.Integer(), server_default="7"),
        sa.Column("max_days_between", sa.Integer(), server_default="30"),
        sa.Column("validity_days", sa.Integer(), server_default="180"),
        sa.Column("price_cents", sa.BigInteger(), server_default="0"),
        sa.Column("is_flexible", sa.Boolean(), server_default="false"),
    )
    op.create_table(
        "course_enrollment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("course_template.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sessions_completed", sa.Integer(), server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), server_default="active"),
    )
    op.create_table(
        "payment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("booking.id", ondelete="SET NULL")),
        sa.Column("amount_cents", sa.BigInteger(), server_default="0"),
        sa.Column("tip_cents", sa.BigInteger(), server_default="0"),
        sa.Column("method", sa.String(32), server_default="cash"),
        sa.Column("external_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "promotion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("discount_percent", sa.Integer()),
        sa.Column("segment", sa.String(64)),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
    )
    op.create_table(
        "promo_code",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("discount_percent", sa.Integer(), server_default="0"),
        sa.Column("max_uses", sa.Integer()),
        sa.Column("uses", sa.Integer(), server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "loyalty_rule",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("every_nth_visit", sa.Integer(), server_default="5"),
        sa.Column("discount_percent", sa.Integer(), server_default="10"),
    )
    op.create_table(
        "payout",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("staff_member_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("staff_member.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), server_default="0"),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "platform_invoice",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), server_default="0"),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (tenant_id::text = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))
            """
        )


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.drop_table(table)

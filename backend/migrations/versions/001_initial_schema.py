"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = [
    "branch",
    "staff_member",
    "client_profile",
    "service_category",
    "service",
    "specialist_service",
    "schedule_template",
    "schedule_exception",
    "booking",
    "booking_item",
    "booking_event",
    "notification",
    "audit_log",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "tenant",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("public_id", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("bot_id", sa.BigInteger(), unique=True),
        sa.Column("bot_username", sa.String(64)),
        sa.Column("bot_token_encrypted", sa.Text()),
        sa.Column("webhook_secret", sa.String(64)),
        sa.Column("bot_status", sa.String(32), server_default="active"),
        sa.Column("brand", postgresql.JSONB(), server_default="{}"),
        sa.Column("rules", postgresql.JSONB(), server_default="{}"),
        sa.Column("subscription_status", sa.String(32), server_default="trial"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "user_account",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "branch",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text()),
        sa.Column("timezone", sa.String(64), server_default="Europe/Moscow"),
        sa.Column("holidays", postgresql.JSONB(), server_default="[]"),
    )
    op.create_index("ix_branch_tenant_id", "branch", ["tenant_id"])

    op.create_table(
        "staff_member",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_account.id", ondelete="SET NULL")),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("roles", postgresql.JSONB(), server_default="[]"),
        sa.Column("photo_url", sa.String(512)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("payout_rule", postgresql.JSONB()),
        sa.UniqueConstraint("tenant_id", "user_account_id", name="uq_staff_tenant_user"),
    )
    op.create_index("ix_staff_member_tenant_id", "staff_member", ["tenant_id"])

    op.create_table(
        "client_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_account.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32)),
        sa.Column("photo_url", sa.String(512)),
        sa.Column("consents", postgresql.JSONB(), server_default="{}"),
        sa.Column("source", sa.String(64)),
        sa.Column("no_show_count", sa.Integer(), server_default="0"),
        sa.Column("telegram_unreachable", sa.Boolean(), server_default="false"),
        sa.Column("tags", postgresql.JSONB(), server_default="[]"),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("tenant_id", "user_account_id", name="uq_client_tenant_user"),
    )
    op.create_index("ix_client_profile_tenant_id", "client_profile", ["tenant_id"])
    op.create_index("ix_client_tenant_phone", "client_profile", ["tenant_id", "phone"])

    op.create_table(
        "service_category",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
    )
    op.create_index("ix_service_category_tenant_id", "service_category", ["tenant_id"])

    op.create_table(
        "service",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("service_category.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), server_default="0"),
        sa.Column("duration_minutes", sa.Integer(), server_default="30"),
        sa.Column("buffer_minutes", sa.Integer(), server_default="0"),
        sa.Column("revisit_days", sa.Integer()),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
    )
    op.create_index("ix_service_tenant_id", "service", ["tenant_id"])

    op.create_table(
        "specialist_service",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("staff_member_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("staff_member.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("service.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price_cents", sa.BigInteger()),
        sa.Column("duration_minutes", sa.Integer()),
        sa.UniqueConstraint("staff_member_id", "service_id", name="uq_specialist_service"),
    )
    op.create_index("ix_specialist_service_tenant_id", "specialist_service", ["tenant_id"])

    op.create_table(
        "schedule_template",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("staff_member_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("staff_member.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.String(8), nullable=False),
        sa.Column("end_time", sa.String(8), nullable=False),
        sa.Column("break_start", sa.String(8)),
        sa.Column("break_end", sa.String(8)),
    )
    op.create_index("ix_schedule_template_tenant_id", "schedule_template", ["tenant_id"])

    op.create_table(
        "schedule_exception",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("staff_member_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("staff_member.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("during", postgresql.TSTZRANGE(), nullable=False),
        sa.Column("note", sa.Text()),
    )
    op.create_index("ix_schedule_exception_tenant_id", "schedule_exception", ["tenant_id"])

    op.create_table(
        "booking",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branch.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), server_default="held"),
        sa.Column("source", sa.String(64)),
        sa.Column("comment", sa.Text()),
        sa.Column("total_price_cents", sa.BigInteger(), server_default="0"),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True)),
        sa.Column("reschedule_pending", sa.Boolean(), server_default="false"),
        sa.Column("course_enrollment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_booking_tenant_id", "booking", ["tenant_id"])

    op.create_table(
        "booking_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("booking.id", ondelete="CASCADE"), nullable=False),
        sa.Column("staff_member_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("staff_member.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("service.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("during", postgresql.TSTZRANGE(), nullable=False),
        sa.Column("blocked_during", postgresql.TSTZRANGE(), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), server_default="0"),
        sa.Column("duration_minutes", sa.Integer(), server_default="30"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
    )
    op.create_index("ix_booking_item_tenant_id", "booking_item", ["tenant_id"])
    op.create_index("ix_booking_item_booking_id", "booking_item", ["booking_id"])

    op.execute(
        """
        ALTER TABLE booking_item
        ADD CONSTRAINT no_specialist_overlap
        EXCLUDE USING gist (staff_member_id WITH =, blocked_during WITH &&)
        WHERE (is_active)
        """
    )

    op.create_table(
        "booking_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("booking.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default="{}"),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_booking_event_tenant_id", "booking_event", ["tenant_id"])

    op.create_table(
        "notification",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("booking.id", ondelete="CASCADE")),
        sa.Column("recipient_type", sa.String(32), nullable=False),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(), server_default="{}"),
    )
    op.create_index("ix_notification_tenant_id", "notification", ["tenant_id"])
    op.execute(
        "CREATE INDEX ix_notification_pending ON notification (send_at) WHERE status = 'pending'"
    )

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("details", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (tenant_id::text = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))
            """
        )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("audit_log")
    op.drop_table("notification")
    op.drop_table("booking_event")
    op.execute("ALTER TABLE booking_item DROP CONSTRAINT IF EXISTS no_specialist_overlap")
    op.drop_table("booking_item")
    op.drop_table("booking")
    op.drop_table("schedule_exception")
    op.drop_table("schedule_template")
    op.drop_table("specialist_service")
    op.drop_table("service")
    op.drop_table("service_category")
    op.drop_table("client_profile")
    op.drop_table("staff_member")
    op.drop_table("branch")
    op.drop_table("user_account")
    op.drop_table("tenant")

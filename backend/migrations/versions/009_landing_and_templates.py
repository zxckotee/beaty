"""Landing page, portfolio, posts, notification templates.

Revision ID: 009
Revises: 008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_landing",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("tagline", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.String(512), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("dgis_url", sa.Text(), nullable=True),
        sa.Column("dgis_firm_id", sa.String(64), nullable=True),
        sa.Column("dgis_complex_id", sa.String(64), nullable=True),
        sa.Column("dgis_embed_html", sa.Text(), nullable=True),
        sa.Column("map_lon", sa.Float(), nullable=True),
        sa.Column("map_lat", sa.Float(), nullable=True),
        sa.Column("map_zoom", sa.Float(), nullable=True),
        sa.Column("is_published", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id"),
    )
    op.create_index("ix_tenant_landing_tenant_id", "tenant_landing", ["tenant_id"])

    op.create_table(
        "landing_portfolio_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("photo_urls", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_index("ix_landing_portfolio_tenant", "landing_portfolio_item", ["tenant_id"])

    op.create_table(
        "landing_post",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("photo_urls", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_visible", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_index("ix_landing_post_tenant", "landing_post", ["tenant_id"])

    op.create_table(
        "notification_template",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("parse_mode", sa.String(16), server_default="HTML", nullable=False),
        sa.Column("photo_slots", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.UniqueConstraint("tenant_id", "kind", name="uq_notification_template_tenant_kind"),
    )
    op.create_index("ix_notification_template_tenant", "notification_template", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("notification_template")
    op.drop_table("landing_post")
    op.drop_table("landing_portfolio_item")
    op.drop_table("tenant_landing")
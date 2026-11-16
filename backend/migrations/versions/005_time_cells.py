"""Open time cells for the web cabinet (manager-defined windows)

Revision ID: 005
Revises: 004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "time_cell",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branch.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "staff_member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff_member.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("allowed_service_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("ends_at > starts_at", name="ck_time_cell_range"),
    )
    op.create_index("ix_time_cell_tenant_id", "time_cell", ["tenant_id"])
    op.create_index("ix_time_cell_tenant_start", "time_cell", ["tenant_id", "starts_at"])
    op.execute(
        """
        ALTER TABLE time_cell
        ADD CONSTRAINT no_cell_overlap
        EXCLUDE USING gist (staff_member_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&)
        """
    )

    op.add_column(
        "booking_item",
        sa.Column(
            "cell_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("time_cell.id", ondelete="SET NULL"), nullable=True
        ),
    )
    op.create_index("ix_booking_item_cell_id", "booking_item", ["cell_id"])
    op.add_column("service", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("service", sa.Column("photo_url", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("service", "photo_url")
    op.drop_column("service", "description")
    op.drop_index("ix_booking_item_cell_id", table_name="booking_item")
    op.drop_column("booking_item", "cell_id")
    op.drop_table("time_cell")

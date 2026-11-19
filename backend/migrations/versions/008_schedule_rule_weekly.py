"""Weekly schedule rule templates; tenant default and staff assignment.

Revision ID: 008
Revises: 007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "schedule_rule",
        sa.Column("days", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.execute(
        """
        UPDATE schedule_rule r
        SET days = (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'weekday', wd,
                        'enabled', wd < 5,
                        'start_time', r.start_time,
                        'end_time', r.end_time,
                        'break_start', r.break_start,
                        'break_end', r.break_end
                    )
                    ORDER BY wd
                ),
                '[]'::jsonb
            )
            FROM generate_series(0, 6) AS wd
        )
        """
    )
    op.drop_column("schedule_rule", "break_end")
    op.drop_column("schedule_rule", "break_start")
    op.drop_column("schedule_rule", "end_time")
    op.drop_column("schedule_rule", "start_time")

    op.add_column(
        "tenant",
        sa.Column(
            "default_schedule_rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("schedule_rule.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "staff_member",
        sa.Column(
            "schedule_rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("schedule_rule.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.drop_column("schedule_template", "rule_id")


def downgrade() -> None:
    op.add_column("schedule_template", sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.drop_column("staff_member", "schedule_rule_id")
    op.drop_column("tenant", "default_schedule_rule_id")
    op.add_column("schedule_rule", sa.Column("start_time", sa.String(8), nullable=True))
    op.add_column("schedule_rule", sa.Column("end_time", sa.String(8), nullable=True))
    op.add_column("schedule_rule", sa.Column("break_start", sa.String(8), nullable=True))
    op.add_column("schedule_rule", sa.Column("break_end", sa.String(8), nullable=True))
    op.execute(
        """
        UPDATE schedule_rule SET
            start_time = COALESCE(days->0->>'start_time', '09:00'),
            end_time = COALESCE(days->0->>'end_time', '18:00')
        """
    )
    op.alter_column("schedule_rule", "start_time", nullable=False)
    op.alter_column("schedule_rule", "end_time", nullable=False)
    op.drop_column("schedule_rule", "days")
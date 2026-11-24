"""tenant landing dgis_locations

Revision ID: 016_dgis_locations
Revises: 015_remove_dual_messenger
Create Date: 2025-11-24

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "016_dgis_locations"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_landing",
        sa.Column("dgis_locations", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
    )
    op.execute(
        """
        UPDATE tenant_landing
        SET dgis_locations = jsonb_build_array(
            jsonb_strip_nulls(
                jsonb_build_object(
                    'firm_id', dgis_firm_id,
                    'dgis_url', dgis_url,
                    'map_lon', map_lon,
                    'map_lat', map_lat,
                    'map_zoom', map_zoom
                )
            )
        )
        WHERE dgis_firm_id IS NOT NULL
          AND dgis_url IS NOT NULL
          AND (dgis_locations IS NULL OR dgis_locations = '[]'::jsonb)
        """
    )


def downgrade() -> None:
    op.drop_column("tenant_landing", "dgis_locations")
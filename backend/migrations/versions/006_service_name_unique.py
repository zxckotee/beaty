"""Deduplicate service names and enforce uniqueness; unique client phone per tenant.

Revision ID: 006
Revises: 005
"""

from collections.abc import Sequence

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                s.id,
                s.tenant_id,
                lower(trim(s.name)) AS norm,
                ROW_NUMBER() OVER (
                    PARTITION BY s.tenant_id, lower(trim(s.name))
                    ORDER BY s.is_active DESC, s.id
                ) AS rn
            FROM service s
        ),
        canon AS (
            SELECT tenant_id, norm, id AS keep_id
            FROM ranked
            WHERE rn = 1
        ),
        doomed AS (
            SELECT r.id AS drop_id, c.keep_id
            FROM ranked r
            JOIN canon c ON c.tenant_id = r.tenant_id AND c.norm = r.norm
            WHERE r.rn > 1
        )
        UPDATE booking_item bi
        SET service_id = d.keep_id
        FROM doomed d
        WHERE bi.service_id = d.drop_id
        """
    )
    op.execute(
        """
        DELETE FROM specialist_service ss
        USING (
            SELECT ss2.ctid
            FROM specialist_service ss1
            JOIN specialist_service ss2
              ON ss1.tenant_id = ss2.tenant_id
             AND ss1.staff_member_id = ss2.staff_member_id
             AND ss1.service_id < ss2.service_id
             AND EXISTS (
                SELECT 1 FROM service a, service b
                WHERE a.id = ss1.service_id AND b.id = ss2.service_id
                  AND a.tenant_id = b.tenant_id
                  AND lower(trim(a.name)) = lower(trim(b.name))
             )
        ) x
        WHERE ss.ctid = x.ctid
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                s.id,
                s.tenant_id,
                lower(trim(s.name)) AS norm,
                ROW_NUMBER() OVER (
                    PARTITION BY s.tenant_id, lower(trim(s.name))
                    ORDER BY s.is_active DESC, s.id
                ) AS rn
            FROM service s
        ),
        canon AS (
            SELECT tenant_id, norm, id AS keep_id
            FROM ranked
            WHERE rn = 1
        ),
        doomed AS (
            SELECT r.id AS drop_id, c.keep_id
            FROM ranked r
            JOIN canon c ON c.tenant_id = r.tenant_id AND c.norm = r.norm
            WHERE r.rn > 1
        )
        UPDATE specialist_service ss
        SET service_id = d.keep_id
        FROM doomed d
        WHERE ss.service_id = d.drop_id
        """
    )
    op.execute(
        """
        DELETE FROM service s
        USING (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY tenant_id, lower(trim(name))
                        ORDER BY is_active DESC, id
                    ) AS rn
                FROM service
            ) z
            WHERE z.rn > 1 AND z.id = s.id
        ) doomed
        WHERE s.id = doomed.id
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_service_tenant_name_norm
        ON service (tenant_id, lower(trim(name)))
        """
    )
    op.execute(
        """
        DELETE FROM client_profile cp1
        USING client_profile cp2
        WHERE cp1.tenant_id = cp2.tenant_id
          AND cp1.phone IS NOT NULL
          AND cp1.phone <> ''
          AND cp1.phone = cp2.phone
          AND cp1.id > cp2.id
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_client_tenant_phone
        ON client_profile (tenant_id, phone)
        WHERE phone IS NOT NULL AND phone <> ''
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_client_tenant_phone")
    op.execute("DROP INDEX IF EXISTS uq_service_tenant_name_norm")
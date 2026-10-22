from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuditLog


async def log_audit(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    details: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            details=details or {},
        )
    )

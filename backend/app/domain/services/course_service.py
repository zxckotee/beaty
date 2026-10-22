from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import CourseEnrollment, CourseTemplate


async def enroll_client(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    template_id: UUID,
    client_profile_id: UUID,
) -> CourseEnrollment:
    template = await session.get(CourseTemplate, template_id)
    if template is None or template.tenant_id != tenant_id:
        raise ValueError("template not found")
    enrollment = CourseEnrollment(
        tenant_id=tenant_id,
        template_id=template_id,
        client_profile_id=client_profile_id,
        expires_at=datetime.now(UTC) + timedelta(days=template.validity_days),
    )
    session.add(enrollment)
    await session.flush()
    return enrollment


async def record_session_completed(
    session: AsyncSession,
    *,
    enrollment_id: UUID,
) -> CourseEnrollment:
    enrollment = await session.get(CourseEnrollment, enrollment_id)
    if enrollment is None:
        raise ValueError("enrollment not found")
    enrollment.sessions_completed += 1
    template = await session.get(CourseTemplate, enrollment.template_id)
    if template and enrollment.sessions_completed >= template.sessions_count:
        enrollment.status = "completed"
    return enrollment

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class TenantContext:
    tenant_id: UUID
    branch_id: UUID
    timezone: str
    public_id: str


@dataclass
class UserContext:
    user_account_id: UUID | None
    telegram_user_id: int | None
    roles: set[str] = field(default_factory=set)
    client_profile_id: UUID | None = None
    staff_member_id: UUID | None = None

    def has_role(self, *names: str) -> bool:
        return bool(self.roles.intersection(names))

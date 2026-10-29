from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy import select

from app.core.db import SessionLocal
from app.domain.models import ClientProfile, StaffMember, Tenant, UserAccount


class BotContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update = event if isinstance(event, Update) else data.get("event_update")
        if not isinstance(update, Update):
            return await handler(event, data)

        bot = data.get("bot")
        tenant_public_id = getattr(bot, "tenant_public_id", None) if bot else None
        if not tenant_public_id:
            return await handler(event, data)

        from_user = None
        if update.message and update.message.from_user:
            from_user = update.message.from_user
        elif update.callback_query and update.callback_query.from_user:
            from_user = update.callback_query.from_user

        async with SessionLocal() as session:
            tenant = await session.scalar(select(Tenant).where(Tenant.public_id == tenant_public_id))
            if tenant is None:
                return await handler(event, data)

            data["tenant"] = tenant
            data["db_session"] = session

            roles: set[str] = {"client"}
            user_account: UserAccount | None = None
            client_profile: ClientProfile | None = None
            staff_member: StaffMember | None = None

            if from_user:
                user_account = await session.scalar(
                    select(UserAccount).where(UserAccount.telegram_user_id == from_user.id)
                )
                if user_account:
                    client_profile = await session.scalar(
                        select(ClientProfile).where(
                            ClientProfile.tenant_id == tenant.id,
                            ClientProfile.user_account_id == user_account.id,
                        )
                    )
                    staff_member = await session.scalar(
                        select(StaffMember).where(
                            StaffMember.tenant_id == tenant.id,
                            StaffMember.user_account_id == user_account.id,
                        )
                    )
                    if staff_member and staff_member.roles:
                        roles.update(staff_member.roles)
                    if staff_member:
                        roles.add("specialist")

            data["user_account"] = user_account
            data["client_profile"] = client_profile
            data["staff_member"] = staff_member
            data["roles"] = roles
            data["subscription_read_only"] = tenant.subscription_status in {
                "expired",
                "suspended",
                "cancelled",
            }

            return await handler(event, data)

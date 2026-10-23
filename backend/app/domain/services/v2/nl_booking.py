"""Phase 3: natural-language booking intent → structured flow."""

from typing import Any
from uuid import UUID


def parse_booking_intent(text: str) -> dict[str, Any]:
    lowered = text.lower()
    intent = "book" if any(w in lowered for w in ("запиш", "book", "стриж")) else "faq"
    return {"intent": intent, "raw": text, "requires_confirmation": True}


async def suggest_slots_from_intent(
    *,
    tenant_id: UUID,
    client_profile_id: UUID,
    text: str,
) -> dict[str, Any]:
    parsed = parse_booking_intent(text)
    return {"tenant_id": str(tenant_id), "client_profile_id": str(client_profile_id), **parsed}

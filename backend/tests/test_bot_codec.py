from uuid import uuid4

from app.domain.models import ClientProfile
from app.domain.services.client_onboarding_service import client_has_phone


def test_client_has_phone_requires_consent_and_length() -> None:
    assert client_has_phone(None) is False
    p = ClientProfile(
        tenant_id=uuid4(),
        user_account_id=uuid4(),
        name="A",
        phone="79991234567",
        consents={"pd_consent": True},
    )
    assert client_has_phone(p) is True
    p.consents = {}
    assert client_has_phone(p) is False

from app.domain.services.team_invite_service import invite_start_param, parse_invite_token


def test_invite_start_param_roundtrip() -> None:
    raw = "abc123token"
    param = invite_start_param(raw)
    assert param.startswith("inv_")
    assert parse_invite_token(param) == raw
    assert parse_invite_token("master_12") is None

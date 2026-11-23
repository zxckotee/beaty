from uuid import UUID

from app.domain.services.message_tokens import TOKEN_PREVIEW_CONTEXT, render_template, staff_media_path


def test_render_template_substitutes_tokens():
    body = "Привет {staff}, {datetime}, {address}"
    text = render_template(body, TOKEN_PREVIEW_CONTEXT)
    assert "Анна" in text
    assert "15.03.2026" in text
    assert "Примерная" in text


def test_render_unknown_token_left_intact():
    text = render_template("{unknown}", TOKEN_PREVIEW_CONTEXT)
    assert text == "{unknown}"


def test_staff_media_path_prefers_url():
    assert staff_media_path(
        photo_url="https://cdn.example/a.jpg",
        photo_file_id="tg123",
        tenant_public_id="salon",
        staff_member_id=UUID("00000000-0000-4000-8000-000000000001"),
    ) == "https://cdn.example/a.jpg"


def test_staff_media_path_falls_back_to_telegram_cache():
    sid = UUID("00000000-0000-4000-8000-0000000000ab")
    assert staff_media_path(
        photo_url=None,
        photo_file_id="AgACAgIAAxk",
        tenant_public_id="demo-salon",
        staff_member_id=sid,
    ) == f"/media/tg/demo-salon/{sid}"


def test_cancel_message_block():
    from dataclasses import replace

    ctx = replace(TOKEN_PREVIEW_CONTEXT, cancel_message="")
    assert render_template("{cancel_message_block}", ctx) == ""
    ctx2 = replace(TOKEN_PREVIEW_CONTEXT, cancel_message="Перенесём на завтра")
    assert "Перенесём" in render_template("{cancel_message_block}", ctx2)
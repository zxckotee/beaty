from app.domain.services.message_tokens import TOKEN_PREVIEW_CONTEXT, render_template


def test_render_template_substitutes_tokens():
    body = "Привет {staff}, {datetime}, {address}"
    text = render_template(body, TOKEN_PREVIEW_CONTEXT)
    assert "Анна" in text
    assert "15.03.2026" in text
    assert "Примерная" in text


def test_render_unknown_token_left_intact():
    text = render_template("{unknown}", TOKEN_PREVIEW_CONTEXT)
    assert text == "{unknown}"
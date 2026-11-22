from app.domain.user_labels import (
    MESSAGE_TOKEN_LABELS,
    booking_status_display,
    message_token_choices,
    staff_roles_display,
)


def test_staff_roles_display_maps_and_dedupes_labels() -> None:
    assert staff_roles_display(["owner", "manager", "specialist"]) == (
        "Владелец, Управляющий, Мастер"
    )
    assert staff_roles_display(["specialist"]) == "Мастер"
    assert staff_roles_display(None) == "—"


def test_booking_status_display() -> None:
    assert booking_status_display("confirmed") == "Подтверждён"
    assert booking_status_display("unknown_code") == "unknown_code"


def test_message_token_choices_covers_all_keys() -> None:
    choices = message_token_choices()
    assert len(choices) == len(MESSAGE_TOKEN_LABELS)
    assert choices[0][0] == "service"
    assert choices[0][1] == "Услуга"
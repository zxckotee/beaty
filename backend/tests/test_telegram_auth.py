import hashlib
import hmac
import time
from urllib.parse import urlencode

from app.core.telegram_auth import verify_telegram_login_widget, verify_webapp_init_data


def test_verify_webapp_init_data() -> None:
    bot_token = "5768333441:AAHkT0X7G8m9Y8Z7X6W5V4U3T2S1R0Q9P8O7N6"
    user = '{"id":12345,"first_name":"Test"}'
    auth_date = str(int(time.time()))
    pairs = {"auth_date": auth_date, "user": user}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    check_hash = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    init_data = urlencode({**pairs, "hash": check_hash})
    parsed = verify_webapp_init_data(init_data, bot_token)
    assert parsed["auth_date"] == auth_date


def test_verify_telegram_login_widget() -> None:
    bot_token = "5768333441:AAHkT0X7G8m9Y8Z7X6W5V4U3T2S1R0Q9P8O7N6"
    auth_date = int(time.time())
    payload = {"id": 12345, "first_name": "Test", "auth_date": auth_date}
    pairs = {k: str(v) for k, v in payload.items()}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    check_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    verified = verify_telegram_login_widget({**payload, "hash": check_hash}, bot_token)
    assert verified["id"] == "12345"

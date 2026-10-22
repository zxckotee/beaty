import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


def verify_webapp_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> dict[str, str]:
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise ValueError("missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        raise ValueError("invalid signature")

    auth_date = int(parsed.get("auth_date", "0"))
    if time.time() - auth_date > max_age_seconds:
        raise ValueError("init data expired")

    if "user" in parsed:
        parsed["user"] = json.loads(parsed["user"])
    return parsed

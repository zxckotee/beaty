"""Safe formatting for bot usernames in Telegram messages."""


def bot_mention_html(username: str | None) -> str:
    """Clickable @mention; use with parse_mode=HTML (Markdown breaks on underscores)."""
    if not username:
        return "ваш бот салона"
    safe = username.replace("&", "&amp;").replace("<", "&lt;")
    return f'<a href="https://t.me/{safe}">@{safe}</a>'

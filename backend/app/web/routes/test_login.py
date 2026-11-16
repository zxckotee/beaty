"""Temporary test login page (user id / @username) until real Telegram auth is wired in prod."""

from __future__ import annotations

import html

from fastapi import APIRouter, Depends, Form
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.settings import get_settings
from app.domain.exceptions import ValidationError
from app.domain.models import Tenant
from app.domain.services.client_service import get_or_create_user_account
from app.web.dev_login import resolve_telegram_user_id
from app.web.routes.auth import _set_session_cookie, dev_login_enabled

router = APIRouter(tags=["test-login"])


def _page(
    *,
    tenants: list[tuple[str, str]],
    selected: str,
    error: str | None = None,
    dev_enabled: bool,
) -> str:
    opts = "".join(
        f'<option value="{html.escape(pid)}"{" selected" if pid == selected else ""}>'
        f"{html.escape(pid)} — {html.escape(name)}</option>"
        for pid, name in tenants
    )
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    disabled_note = ""
    if not dev_enabled:
        disabled_note = (
            "<p class=\"muted\">Тестовый вход выключен. Задайте <code>WEB_DEV_LOGIN=true</code> "
            "или <code>ENVIRONMENT=development</code> в .env и перезапустите сервис <code>web</code>.</p>"
        )
    form = ""
    if dev_enabled and tenants:
        form = f"""
<form method="post" action="/login">
  <label>Салон (tenant)
    <select name="tenant_public_id" required>{opts}</select>
  </label>
  <label>Telegram user id или @username
    <input name="identifier" required autocomplete="username"
           placeholder="100001 или @myusername" />
  </label>
  <label>Имя в кабинете (необязательно)
    <input name="display_name" autocomplete="name" placeholder="как показывать на сайте" />
  </label>
  <button type="submit">Войти</button>
</form>
<p class="muted">Числовой <strong>user id</strong> — надёжный вариант (seed owner: <code>100001</code>).
Кабинет: <code>/t/&lt;tenant&gt;/</code>.</p>
"""
    links = " ".join(f'<a href="/t/{html.escape(pid)}/">{html.escape(pid)}</a>' for pid, _ in tenants)
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Beaty — тестовый вход</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 28rem; margin: 2rem auto; }}
    h1 {{ font-size: 1.35rem; }}
    label {{ display: block; margin: 0.75rem 0; font-size: 0.9rem; }}
    input, select, button {{ width: 100%; box-sizing: border-box; padding: 0.5rem; font-size: 1rem; }}
    button {{ margin-top: 0.5rem; background: #2481cc; color: #fff; border: none;
              border-radius: 8px; cursor: pointer; }}
    .err {{ color: #b00020; background: #fde8e8; padding: 0.5rem 0.75rem; border-radius: 8px; }}
    .muted {{ color: #555; font-size: 0.88rem; }}
    code {{ font-size: 0.85em; }}
  </style>
</head>
<body>
  <h1>Beaty — тестовый вход</h1>
  <p>Временная страница для проверки кабинета без OAuth через Telegram.</p>
  {disabled_note}
  {err}
  {form}
  <p class="muted">Салоны: {links or "нет в базе"}</p>
</body>
</html>"""


async def _tenant_choices(session: AsyncSession) -> list[tuple[str, str]]:
    rows = (await session.execute(select(Tenant.public_id, Tenant.name).order_by(Tenant.name))).all()
    return [(pid, name or pid) for pid, name in rows]


@router.get("/", response_model=None)
async def root_login(session: AsyncSession = Depends(get_session)) -> HTMLResponse | RedirectResponse:
    settings = get_settings()
    dev = dev_login_enabled()
    tenants = await _tenant_choices(session)

    if settings.web_default_tenant and dev:
        return HTMLResponse(_page(tenants=tenants, selected=settings.web_default_tenant, dev_enabled=dev))
    if settings.web_default_tenant and not dev:
        return RedirectResponse(f"/t/{settings.web_default_tenant}/", status_code=302)
    if len(tenants) == 1 and not dev:
        return RedirectResponse(f"/t/{tenants[0][0]}/", status_code=302)
    if dev:
        selected = tenants[0][0] if tenants else ""
        return HTMLResponse(_page(tenants=tenants, selected=selected, dev_enabled=True))
    return HTMLResponse(
        _page(
            tenants=tenants,
            selected=tenants[0][0] if tenants else "",
            error="Нет маршрута по умолчанию. Откройте /t/<public_id>/ или включите WEB_DEV_LOGIN.",
            dev_enabled=False,
        )
    )


@router.get("/login", response_class=HTMLResponse)
async def login_get(
    session: AsyncSession = Depends(get_session),
    tenant: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    tenants = await _tenant_choices(session)
    selected = tenant or get_settings().web_default_tenant or (tenants[0][0] if tenants else "")
    return HTMLResponse(_page(tenants=tenants, selected=selected, error=error, dev_enabled=dev_login_enabled()))


@router.post("/login", response_model=None)
async def login_post(
    tenant_public_id: str = Form(...),
    identifier: str = Form(...),
    display_name: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse | HTMLResponse:
    if not dev_login_enabled():
        raise HTTPException(status_code=403, detail="test login disabled")
    tenant = await session.scalar(select(Tenant).where(Tenant.public_id == tenant_public_id))
    if tenant is None:
        tenants = await _tenant_choices(session)
        return HTMLResponse(
            _page(tenants=tenants, selected=tenant_public_id, error="салон не найден", dev_enabled=True),
            status_code=400,
        )
    try:
        telegram_user_id, auto_name = await resolve_telegram_user_id(tenant, identifier)
    except ValidationError as exc:
        tenants = await _tenant_choices(session)
        return HTMLResponse(
            _page(tenants=tenants, selected=tenant_public_id, error=str(exc), dev_enabled=True),
            status_code=400,
        )
    user = await get_or_create_user_account(session, telegram_user_id)
    await session.commit()
    response = RedirectResponse(f"/t/{tenant.public_id}/", status_code=303)
    _set_session_cookie(response, tenant, user.id, (display_name or auto_name or "").strip() or None)
    return response
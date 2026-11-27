"""QR code PNG for Telegram deep links."""

from __future__ import annotations

import io

import segno


def qr_png_bytes(url: str, *, scale: int = 8, border: int = 2) -> bytes:
    qr = segno.make(url, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=border)
    return buf.getvalue()
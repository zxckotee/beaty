from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.settings import get_settings

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)


def media_root() -> Path:
    root = Path(get_settings().media_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _detect_extension(head: bytes) -> str | None:
    for magic, ext in _SIGNATURES:
        if head.startswith(magic):
            return ext
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


async def save_image(upload: UploadFile, tenant_id: uuid.UUID) -> str:
    """Store an uploaded image and return its public URL. Validates size and magic bytes."""
    limit = get_settings().web_max_upload_bytes
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail="file too large")
    ext = _detect_extension(data[:16])
    if ext is None:
        raise HTTPException(status_code=415, detail="unsupported image format")
    folder = media_root() / str(tenant_id)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    (folder / name).write_bytes(data)
    return f"/media/{tenant_id}/{name}"

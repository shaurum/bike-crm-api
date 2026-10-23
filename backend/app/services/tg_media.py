"""Скачивание файлов Telegram в uploads/messages для чатов."""

import logging
import mimetypes
import os
import uuid
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_FILES_PER_MESSAGE = 5
REQUEST_TIMEOUT = 30.0

_EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "video/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "application/zip": ".zip",
}


def _safe_ext(path: str, content_type: Optional[str]) -> str:
    ext = os.path.splitext(path or "")[1].lower()
    if ext and len(ext) <= 8 and ext[1:].isalnum():
        return ext
    if content_type in _EXT_BY_MIME:
        return _EXT_BY_MIME[content_type]
    guessed = mimetypes.guess_extension(content_type or "")
    if guessed and len(guessed) <= 8:
        return guessed
    return ".bin"


async def save_tg_file(
    token: str,
    file_id: str,
    *,
    name: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[dict]:
    """getFile → скачивание → сохранение в uploads/messages.

    Возвращает {url, name, content_type} или None при ошибке.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True)
    try:
        info = await client.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": file_id},
        )
        info.raise_for_status()
        file_path = (info.json().get("result") or {}).get("file_path") or ""
        if not file_path:
            return None
        file_resp = await client.get(
            f"https://api.telegram.org/file/bot{token}/{file_path}"
        )
        file_resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram: файл %s не скачан: %s", file_id, exc)
        return None
    finally:
        if owns_client:
            await client.aclose()

    content_type = (
        file_resp.headers.get("content-type") or ""
    ).split(";")[0].strip() or None
    ext = _safe_ext(file_path, content_type)
    if content_type is None:
        content_type = mimetypes.guess_type("x" + ext)[0]

    resolved_name = name or os.path.basename(file_path)
    if not resolved_name or resolved_name == file_path:
        resolved_name = f"file-{uuid.uuid4().hex[:8]}{ext}"

    filename = f"tg-{uuid.uuid4().hex}{ext}"
    target_dir = os.path.join(settings.UPLOAD_DIR, "messages")
    os.makedirs(target_dir, exist_ok=True)
    try:
        with open(os.path.join(target_dir, filename), "wb") as fh:
            fh.write(file_resp.content)
    except OSError as exc:
        logger.warning("Telegram: файл не сохранён: %s", exc)
        return None

    return {
        "url": f"/uploads/messages/{filename}",
        "name": resolved_name,
        "content_type": content_type,
    }


def _pick_media(message: dict) -> list[dict]:
    """Извлекает файлы из Telegram-update: photo/document/video/..."""
    found: list[dict] = []
    photo = message.get("photo")
    if isinstance(photo, list) and photo:
        best = photo[-1]  # самое крупное разрешение
        found.append({"kind": "photo", "file_id": best.get("file_id")})
    for kind in ("document", "video", "audio", "voice", "animation"):
        item = message.get(kind)
        if isinstance(item, dict) and item.get("file_id"):
            found.append({"kind": kind, "file_id": item.get("file_id")})
    sticker = message.get("sticker")
    if isinstance(sticker, dict) and sticker.get("file_id") and not sticker.get("is_video"):
        found.append({"kind": "sticker", "file_id": sticker.get("file_id")})
    return found[:MAX_FILES_PER_MESSAGE]


async def extract_attachments(token: str, message: dict) -> list[dict]:
    """Скачивает файлы сообщения в uploads/messages и возвращает описания.

    Ошибка на одном файле не прерывает остальные и не теряет сообщение.
    """
    items = _pick_media(message)
    if not items:
        return []

    out: list[dict] = []
    document = message.get("document") or {}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        for item in items:
            file_id = str(item.get("file_id") or "")
            if not file_id:
                continue
            name = None
            if item["kind"] == "document" and isinstance(document, dict):
                name = document.get("file_name")
            saved = await save_tg_file(token, file_id, name=name, client=client)
            if saved:
                out.append(saved)
    return out

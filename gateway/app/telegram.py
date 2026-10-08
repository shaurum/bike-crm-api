"""Клиент Telegram Bot API: long-polling входящих и отправка ответов.

Состояние (offset) хранится в JSON-файле, чтобы после рестарта
не перечитывать старые апдейты. Дубли и так отсекает уникальный
индекс очереди, но offset экономит запросы.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

API_BASE = "https://api.telegram.org"
TIMEOUT = 60.0
CONFIG_PATH = os.environ.get("TELEGRAM_CONFIG", "/data/telegram.json")
_lock = threading.Lock()


class TelegramError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def bot_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def load_config() -> dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (ValueError, OSError):
        return {}


def save_config(patch: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        current = load_config()
        current.update({k: v for k, v in patch.items() if v is not None})
        directory = os.path.dirname(CONFIG_PATH)
        if directory:
            os.makedirs(directory, exist_ok=True)
        temporary = CONFIG_PATH + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(current, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, CONFIG_PATH)
        return current


async def call(method: str, **params: Any) -> Any:
    token = bot_token()
    if not token:
        raise TelegramError("TELEGRAM_BOT_TOKEN не задан")

    url = f"{API_BASE}/bot{token}/{method}"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.post(url, json=params)
        except httpx.HTTPError as exc:
            raise TelegramError(f"Telegram недоступен: {exc}") from exc

    try:
        body = response.json()
    except ValueError:
        body = {}

    if response.status_code >= 400 or not body.get("ok", False):
        description = str(body.get("description") or f"HTTP {response.status_code}")
        if "Too Many Requests" in description or "429" in str(
            (body.get("parameters") or {}).get("retry_after", "")
        ):
            raise TelegramError(description, status_code=429)
        raise TelegramError(description, status_code=response.status_code)

    return body.get("result")


async def get_me() -> dict[str, Any]:
    return await call("getMe")


async def get_updates(offset: int, timeout: int = 50) -> list[dict[str, Any]]:
    result = await call(
        "getUpdates",
        offset=offset,
        timeout=timeout,
        allowed_updates=["message"],
    )
    return result or []


async def send_message(chat_id: str, text: str) -> str:
    result = await call("sendMessage", chat_id=chat_id, text=text[:4096])
    if isinstance(result, dict) and result.get("message_id") is not None:
        return str(result["message_id"])
    return ""


def message_text(message: dict[str, Any]) -> str:
    """Текст сообщения; вложения и стикеры превращаем в понятную заглушку."""
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    caption = message.get("caption")
    if isinstance(caption, str) and caption.strip():
        return caption.strip()
    kind = message.get("photo") and "фото" or None
    if message.get("sticker"):
        kind = "стикер"
    elif message.get("voice"):
        kind = "голосовое сообщение"
    elif message.get("video"):
        kind = "видео"
    elif message.get("document"):
        kind = "документ"
    elif message.get("contact"):
        kind = "контакт"
    return f"[{kind}]" if kind else ""


def sender_name(message: dict[str, Any]) -> Optional[str]:
    user = message.get("from") or {}
    name = " ".join(
        part
        for part in (str(user.get("first_name") or ""), str(user.get("last_name") or ""))
        if part
    ).strip()
    return name or None


def iso_from_unix(value: Any) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None

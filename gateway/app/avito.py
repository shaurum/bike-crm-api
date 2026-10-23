"""Клиент Авито и хранение его токенов на шлюзе."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

API_BASE = "https://api.avito.ru"
AUTHORIZE_URL = "https://avito.ru/oauth"
TOKEN_URL = f"{API_BASE}/token"
DEFAULT_SCOPES = "messenger:read,messenger:write,user:read"
REFRESH_MARGIN = timedelta(minutes=20)
TIMEOUT = 20.0

CONFIG_PATH = os.environ.get("AVITO_CONFIG", "/data/avito.json")
_lock = threading.Lock()


class AvitoError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def load_config() -> dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


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


def drop_tokens() -> dict[str, Any]:
    with _lock:
        current = load_config()
        for key in ("access_token", "refresh_token", "token_expires_at", "user_id"):
            current.pop(key, None)
        with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
            json.dump(current, handle, ensure_ascii=False, indent=2)
        return current


def build_connect_url(
    client_id: str,
    redirect_uri: str,
    scopes: str = DEFAULT_SCOPES,
    state: Optional[str] = None,
) -> str:
    from urllib.parse import urlencode

    payload = {
        "response_type": "code",
        "pro_users_flow": "true",
        "client_id": client_id,
        "scope": scopes,
        "redirect_uri": redirect_uri,
    }
    if state:
        payload["state"] = state
    return AUTHORIZE_URL + "?" + urlencode(payload)


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return (response.text or "").strip()[:200] or f"HTTP {response.status_code}"
    if isinstance(body, dict):
        return str(body.get("error_description") or body.get("error") or body)[:200]
    return str(body)[:200]


async def _token_request(payload: dict[str, str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.post(TOKEN_URL, data=payload)
        except httpx.HTTPError as exc:
            raise AvitoError(f"Авито недоступен: {exc}") from exc
    if response.status_code >= 400:
        raise AvitoError(
            f"Авито отклонил запрос токена: {_detail(response)}",
            status_code=response.status_code,
        )
    return response.json()


async def exchange_code(code: str) -> dict[str, Any]:
    config = load_config()
    client_id = config.get("client_id")
    client_secret = config.get("client_secret")
    redirect_uri = config.get("redirect_uri")
    if not client_id or not client_secret or not redirect_uri:
        raise AvitoError("Сначала сохраните client_id, client_secret и redirect_uri")

    payload = await _token_request(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        }
    )
    return _store_tokens(payload)


def _store_tokens(payload: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "access_token": payload.get("access_token"),
        "refresh_token": payload.get("refresh_token"),
    }
    expires_in = payload.get("expires_in")
    if expires_in:
        patch["token_expires_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        ).isoformat()
    return save_config(patch)


def _expiry(config: dict[str, Any]) -> Optional[datetime]:
    raw = config.get("token_expires_at")
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


async def refresh_token() -> dict[str, Any]:
    config = load_config()
    client_id = config.get("client_id")
    client_secret = config.get("client_secret")
    refresh = config.get("refresh_token")
    if not client_id or not client_secret or not refresh:
        raise AvitoError("Авито не подключён на шлюзе")

    payload = await _token_request(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh,
        }
    )
    return _store_tokens(payload)


async def access_token() -> str:
    config = load_config()
    token = config.get("access_token")
    if not token:
        raise AvitoError("Авито не подключён на шлюзе")
    expiry = _expiry(config)
    if not expiry or expiry - datetime.now(timezone.utc) < REFRESH_MARGIN:
        config = await refresh_token()
        token = config.get("access_token")
    if not token:
        raise AvitoError("Не удалось получить токен Авито")
    return str(token)


async def request(
    method: str, path: str, *, json_body: Optional[dict] = None, params: Optional[dict] = None
) -> Any:
    token = await access_token()
    url = path if path.startswith("http") else API_BASE + path
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=json_body,
                params=params,
            )
        except httpx.HTTPError as exc:
            raise AvitoError(f"Авито недоступен: {exc}") from exc

    if response.status_code == 401:
        await refresh_token()
        token = await access_token()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=json_body,
                params=params,
            )

    if response.status_code >= 400:
        raise AvitoError(
            f"Авито ответил ошибкой: {_detail(response)}", status_code=response.status_code
        )
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text


async def fetch_account() -> dict[str, Any]:
    data = await request("GET", "/core/v1/accounts/self")
    if not isinstance(data, dict) or "id" not in data:
        raise AvitoError("Авито не вернул идентификатор аккаунта")
    save_config(
        {
            "user_id": int(data["id"]),
            "account_name": data.get("name"),
            "account_phone": data.get("phone"),
        }
    )
    return data


async def list_chats(user_id: str) -> list[dict[str, Any]]:
    data = await request("GET", f"/messenger/v2/accounts/{user_id}/chats")
    if isinstance(data, dict):
        return data.get("chats") or []
    return data if isinstance(data, list) else []


async def list_messages(user_id: str, chat_id: str, limit: int = 50) -> list[dict[str, Any]]:
    data = await request(
        "GET",
        f"/messenger/v3/accounts/{user_id}/chats/{chat_id}/messages/",
        params={"limit": limit},
    )
    if isinstance(data, dict):
        return data.get("items") or data.get("messages") or []
    return data if isinstance(data, list) else []


async def send_text(user_id: str, chat_id: str, text: str) -> str:
    data = await request(
        "POST",
        f"/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages",
        json_body={"type": "text", "message": {"text": text[:1000]}},
    )
    if isinstance(data, dict) and data.get("id"):
        return str(data["id"])
    return ""


def message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    text = content.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    if isinstance(content, str) and content.strip():
        return content.strip()
    return f"[{message.get('type') or 'сообщение'}]"


def message_media(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Вложения сообщения Авито: URL картинки или файла из content."""
    content = message.get("content") or {}
    if not isinstance(content, dict):
        return []
    out: list[dict[str, Any]] = []

    def _url_of(value: Any) -> Optional[str]:
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
        if isinstance(value, dict):
            for key in ("url", "original", "large", "small", "thumb"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                    return candidate
        return None

    image_url = _url_of(content.get("image"))
    if image_url:
        out.append({"url": image_url, "content_type": "image/jpeg"})

    file_value = content.get("file")
    file_url = _url_of(file_value)
    if file_url:
        entry: dict[str, Any] = {"url": file_url}
        if isinstance(file_value, dict):
            if file_value.get("name") or file_value.get("file_name"):
                entry["name"] = file_value.get("name") or file_value.get("file_name")
            if file_value.get("content_type") or file_value.get("type"):
                entry["content_type"] = (
                    file_value.get("content_type") or file_value.get("type")
                )
        out.append(entry)
    return out[:5]


def counterparty_id(chat: dict[str, Any], own_user_id: Any) -> Optional[str]:
    for user in chat.get("users") or []:
        if not isinstance(user, dict):
            continue
        if str(user.get("id")) == str(own_user_id):
            continue
        if user.get("id") is not None:
            return str(user["id"])
    return None


def counterparty_name(chat: dict[str, Any], own_user_id: Any) -> Optional[str]:
    for user in chat.get("users") or []:
        if not isinstance(user, dict):
            continue
        if str(user.get("id")) == str(own_user_id):
            continue
        if user.get("name"):
            return str(user["name"])
    return None

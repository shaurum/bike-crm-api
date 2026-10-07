"""Интеграция с Авито: OAuth-токены и Messenger API.

Токен доступа живёт 24 часа, поэтому все запросы идут через
`get_access_token`, который сам продлевает токен по refresh_token.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IntegrationSetting

logger = logging.getLogger(__name__)

API_BASE = "https://api.avito.ru"
AUTHORIZE_URL = "https://avito.ru/oauth"
TOKEN_URL = f"{API_BASE}/token"
DEFAULT_SCOPES = "messenger:read,messenger:write,user:read"
REFRESH_MARGIN = timedelta(minutes=20)
REQUEST_TIMEOUT = 20.0


class AvitoError(Exception):
    """Ошибка настроек или ответа Авито."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


async def load_integration(db: AsyncSession) -> IntegrationSetting:
    result = await db.execute(
        select(IntegrationSetting).where(IntegrationSetting.name == "avito")
    )
    item = result.scalars().first()
    if not item:
        raise AvitoError("Интеграция «Авито» не заведена в базе")
    return item


def build_connect_url(
    client_id: str,
    redirect_uri: str,
    scopes: str = DEFAULT_SCOPES,
) -> str:
    from urllib.parse import urlencode

    return AUTHORIZE_URL + "?" + urlencode(
        {
            "response_type": "code",
            "pro_users_flow": "true",
            "client_id": client_id,
            "scope": scopes,
            "redirect_uri": redirect_uri,
        }
    )


async def _token_request(payload: dict[str, str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.post(TOKEN_URL, data=payload)
        except httpx.HTTPError as exc:
            raise AvitoError(f"Не удалось достучаться до Авито: {exc}") from exc

    if response.status_code >= 400:
        detail = _error_detail(response)
        raise AvitoError(
            f"Авито отклонил запрос токена: {detail}", status_code=response.status_code
        )
    return response.json()


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return (response.text or "").strip()[:200] or f"HTTP {response.status_code}"
    if isinstance(body, dict):
        return str(body.get("error_description") or body.get("error") or body)[:200]
    return str(body)[:200]


def _parse_expiry(payload: dict[str, Any]) -> Optional[datetime]:
    expires_in = payload.get("expires_in")
    if not expires_in:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))


async def _store_tokens(item: IntegrationSetting, payload: dict[str, Any]) -> None:
    secret = dict(item.secret or {})
    config = dict(item.config or {})
    if payload.get("access_token"):
        secret["access_token"] = payload["access_token"]
    if payload.get("refresh_token"):
        secret["refresh_token"] = payload["refresh_token"]
    expiry = _parse_expiry(payload)
    config["token_expires_at"] = expiry.isoformat() if expiry else None
    item.secret = secret
    item.config = config


async def exchange_code(db: AsyncSession, code: str) -> IntegrationSetting:
    """Меняет код авторизации на токены и сохраняет их."""
    item = await load_integration(db)
    secret = item.secret or {}
    client_id = secret.get("client_id")
    client_secret = secret.get("client_secret")
    redirect_uri = (item.config or {}).get("redirect_uri")
    if not client_id or not client_secret:
        raise AvitoError("Сначала сохраните client_id и client_secret приложения")
    if not redirect_uri:
        raise AvitoError("Сначала сохраните redirect_uri приложения")

    payload = await _token_request(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        }
    )
    await _store_tokens(item, payload)
    config = dict(item.config or {})
    config["connected_at"] = datetime.now(timezone.utc).isoformat()
    item.config = config
    await db.commit()
    await db.refresh(item)
    return item


def _expiry_of(item: IntegrationSetting) -> Optional[datetime]:
    raw = (item.config or {}).get("token_expires_at")
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


async def refresh_access_token(
    db: AsyncSession, item: Optional[IntegrationSetting] = None
) -> IntegrationSetting:
    item = item or await load_integration(db)
    secret = item.secret or {}
    client_id = secret.get("client_id")
    client_secret = secret.get("client_secret")
    refresh_token = secret.get("refresh_token")
    if not client_id or not client_secret:
        raise AvitoError("Не заданы client_id и client_secret приложения")
    if not refresh_token:
        raise AvitoError("Авито не подключён: сначала авторизуйте приложение")

    payload = await _token_request(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }
    )
    await _store_tokens(item, payload)
    await db.commit()
    await db.refresh(item)
    logger.info("Avito access token refreshed")
    return item


async def get_access_token(db: AsyncSession) -> str:
    item = await load_integration(db)
    secret = item.secret or {}
    token = secret.get("access_token")
    expiry = _expiry_of(item)
    if not token:
        raise AvitoError("Авито не подключён: авторизуйте приложение в настройках")
    if not expiry or expiry - datetime.now(timezone.utc) < REFRESH_MARGIN:
        item = await refresh_access_token(db, item)
        token = (item.secret or {}).get("access_token")
    if not token:
        raise AvitoError("Не удалось получить токен доступа к Авито")
    return token


async def _request(
    db: AsyncSession,
    method: str,
    path: str,
    *,
    json_body: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
) -> Any:
    token = await get_access_token(db)
    url = path if path.startswith("http") else API_BASE + path
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=json_body,
                params=params,
            )
        except httpx.HTTPError as exc:
            raise AvitoError(f"Не удалось достучаться до Авито: {exc}") from exc

    if response.status_code == 401:
        item = await refresh_access_token(db)
        token = (item.secret or {}).get("access_token")
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=json_body,
                params=params,
            )

    if response.status_code >= 400:
        raise AvitoError(
            f"Авито ответил ошибкой: {_error_detail(response)}",
            status_code=response.status_code,
        )
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text


async def fetch_account(db: AsyncSession) -> dict[str, Any]:
    """Данные авторизованного аккаунта, включая id пользователя."""
    data = await _request(db, "GET", "/core/v1/accounts/self")
    if not isinstance(data, dict) or "id" not in data:
        raise AvitoError("Авито не вернул идентификатор аккаунта")
    return data


async def save_account(db: AsyncSession, account: dict[str, Any]) -> IntegrationSetting:
    item = await load_integration(db)
    config = dict(item.config or {})
    config["user_id"] = int(account["id"])
    config["account_name"] = account.get("name")
    config["account_phone"] = account.get("phone")
    item.config = config
    item.is_enabled = True
    await db.commit()
    await db.refresh(item)
    return item


def account_user_id(item: IntegrationSetting) -> str:
    user_id = (item.config or {}).get("user_id")
    if not user_id:
        raise AvitoError("Авито не подключён: нет id аккаунта")
    return str(user_id)


async def send_text(db: AsyncSession, user_id: str, chat_id: str, text: str) -> str:
    data = await _request(
        db,
        "POST",
        f"/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages",
        json_body={"type": "text", "message": {"text": text[:1000]}},
    )
    if isinstance(data, dict) and data.get("id"):
        return str(data["id"])
    return ""


async def list_chats(db: AsyncSession, user_id: str) -> list[dict[str, Any]]:
    data = await _request(db, "GET", f"/messenger/v2/accounts/{user_id}/chats")
    if isinstance(data, dict):
        return data.get("chats") or []
    return data if isinstance(data, list) else []


async def list_messages(
    db: AsyncSession, user_id: str, chat_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    data = await _request(
        db,
        "GET",
        f"/messenger/v3/accounts/{user_id}/chats/{chat_id}/messages/",
        params={"limit": limit},
    )
    if isinstance(data, dict):
        return data.get("items") or data.get("messages") or []
    return data if isinstance(data, list) else []


async def mark_chat_read(db: AsyncSession, user_id: str, chat_id: str) -> None:
    try:
        await _request(
            db,
            "POST",
            f"/messenger/v1/accounts/{user_id}/chats/{chat_id}/read",
            json_body={},
        )
    except AvitoError as exc:
        logger.warning("Avito mark read failed for %s: %s", chat_id, exc)


async def subscribe_webhook(url: str, access_token: str) -> None:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(
            f"{API_BASE}/messenger/v3/webhook",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"url": url},
        )
    if response.status_code >= 400:
        raise AvitoError(
            f"Не удалось подписаться на уведомления Авито: {_error_detail(response)}",
            status_code=response.status_code,
        )


async def unsubscribe_webhook(url: str, access_token: str) -> None:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        await client.post(
            f"{API_BASE}/messenger/v1/webhook/unsubscribe",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"url": url},
        )


def message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    text = content.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    if isinstance(content, str):
        return content.strip()
    kind = message.get("type") or "сообщение"
    return f"[{kind}]"


def _counterparty_users(chat: dict[str, Any], own_user_id: Any) -> list[dict[str, Any]]:
    users = chat.get("users") or []
    return [
        user
        for user in users
        if isinstance(user, dict) and str(user.get("id")) != str(own_user_id)
    ]


def counterparty_id(chat: dict[str, Any], own_user_id: Any) -> Optional[str]:
    """Стабильный идентификатор собеседника для поиска контакта в CRM."""
    for user in _counterparty_users(chat, own_user_id):
        if user.get("id") is not None:
            return str(user["id"])
    return None


def counterparty_name(chat: dict[str, Any], own_user_id: Any) -> Optional[str]:
    for user in _counterparty_users(chat, own_user_id):
        if user.get("name"):
            return str(user["name"])
    return None


def chat_item_title(chat: dict[str, Any]) -> Optional[str]:
    context = chat.get("context") or {}
    value = context.get("value") or {}
    if isinstance(value, dict) and value.get("title"):
        return str(value["title"])
    return None

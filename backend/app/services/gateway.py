"""Клиент облачного шлюза интеграций (очередь событий)."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

TIMEOUT = 25.0


class GatewayError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def gateway_url() -> str:
    return os.environ.get("GATEWAY_URL", "").strip().rstrip("/")


def gateway_token() -> str:
    return os.environ.get("GATEWAY_TOKEN", "").strip()


def is_configured() -> bool:
    return bool(gateway_url() and gateway_token())


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {gateway_token()}"}


async def _request(
    method: str,
    path: str,
    *,
    json_body: Optional[dict] = None,
    params: Optional[dict] = None,
) -> Any:
    if not is_configured():
        raise GatewayError("Шлюз не настроен: задайте GATEWAY_URL и GATEWAY_TOKEN")

    url = gateway_url() + path
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.request(
                method, url, headers=_headers(), json=json_body, params=params
            )
    except httpx.HTTPError as exc:
        raise GatewayError(f"Шлюз недоступен: {exc}") from exc

    if response.status_code >= 400:
        detail = _detail(response, status=response.status_code)
        raise GatewayError(detail, status_code=response.status_code)
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError as exc:
        raise GatewayError("Шлюз ответил неожиданным форматом") from exc


def _detail(response: httpx.Response, *, status: int) -> str:
    try:
        body = response.json()
    except ValueError:
        return (response.text or "").strip()[:200] or f"HTTP {status}"
    if isinstance(body, dict):
        return str(body.get("detail") or body.get("error") or body)[:200]
    return str(body)[:200]


async def get_status() -> dict[str, Any]:
    return await _request("GET", "/status")


async def pull_events(after: int = 0, limit: int = 100) -> dict[str, Any]:
    return await _request("GET", "/events", params={"after": after, "limit": limit})


async def enqueue_outbound(chat_id: str, text: str, source: str = "avito") -> dict[str, Any]:
    return await _request(
        "POST",
        "/outbox",
        json_body={"items": [{"source": source, "chat_id": chat_id, "text": text}]},
    )


async def avito_config(patch: dict[str, Any]) -> dict[str, Any]:
    return await _request("POST", "/avito/config", json_body=patch)


async def avito_connect_url() -> dict[str, Any]:
    return await _request("POST", "/avito/connect-url")


async def avito_disconnect() -> dict[str, Any]:
    return await _request("POST", "/avito/disconnect")

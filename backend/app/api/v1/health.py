"""Health: базовые заглушки и реальные проверки сервисов для индикаторов в UI."""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

CACHE_TTL = 10.0
_cache: Dict[str, Any] = {"at": 0.0, "data": None}

SERVICE_KEYS = ("postgres", "redis", "celery", "gateway", "avito", "telegram", "email")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _brief(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:160]


async def _check_postgres(db: AsyncSession) -> dict:
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("health: postgres down: %s", exc)
        return {"status": "down", "detail": _brief(exc)}


async def _check_redis() -> dict:
    client = aioredis.from_url(
        str(settings.REDIS_URL), socket_connect_timeout=2, socket_timeout=2
    )
    try:
        await client.ping()
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "detail": _brief(exc)}
    finally:
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001
            pass


async def _check_celery() -> dict:
    from app.tasks.celery_app import celery_app

    try:
        replies: List[dict] = await asyncio.wait_for(
            asyncio.to_thread(celery_app.control.ping, timeout=2.0), timeout=5.0
        )
        if replies:
            return {"status": "ok", "detail": f"воркеров: {len(replies)}"}
        return {"status": "down", "detail": "нет живых воркеров"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "detail": _brief(exc)}


async def _check_gateway() -> tuple[dict, Optional[dict]]:
    """Сам шлюз + данные из его /status (авито/телеграм)."""
    from app.services import gateway

    if not gateway.is_configured():
        return {"status": "off", "detail": "не настроен"}, None

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{gateway.gateway_url()}/status",
                headers={"Authorization": f"Bearer {gateway.gateway_token()}"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "detail": _brief(exc)}, None

    return {"status": "ok"}, data


def _check_avito(gw_status: Optional[dict]) -> dict:
    if not gw_status:
        return {"status": "off", "detail": "шлюз недоступен"}
    avito = gw_status.get("avito") or {}
    if not avito.get("configured"):
        return {"status": "off", "detail": "не настроен"}
    if avito.get("paywall"):
        return {
            "status": "warn",
            "detail": "Исходящие заблокированы: не оплачен тариф «Расширенный»",
        }
    if avito.get("connected"):
        return {"status": "ok", "detail": f"аккаунт {avito.get('account_name') or avito.get('user_id')}"}
    return {"status": "warn", "detail": "настроен, но не подключён"}


def _check_telegram(gw_status: Optional[dict]) -> dict:
    if not gw_status:
        return {"status": "off", "detail": "шлюз недоступен"}
    tg = gw_status.get("telegram") or {}
    if tg.get("configured"):
        return {"status": "ok", "detail": f"@{tg.get('username') or '…'}"}
    return {"status": "off", "detail": "бот не настроен"}


async def _check_email(db: AsyncSession) -> dict:
    from app.services.mail import get_mail_settings

    try:
        mail = await get_mail_settings(db)
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "detail": _brief(exc)}

    if not mail.is_ready():
        return {"status": "off", "detail": "SMTP не настроен"}

    if mail.provider == "smtp" and mail.host:
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(mail.host, mail.port), timeout=3.0
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
            return {"status": "ok", "detail": f"{mail.host}:{mail.port}"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "down", "detail": _brief(exc)}

    return {"status": "ok", "detail": mail.provider}


async def _last_ok_map() -> Dict[str, Optional[str]]:
    """Когда сервис最后一次 был ok (хранится в redis, переживает рестарты)."""
    try:
        client = aioredis.from_url(str(settings.REDIS_URL), socket_connect_timeout=2)
        try:
            values = await client.mget(*[f"health:last_ok:{k}" for k in SERVICE_KEYS])
        finally:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass
        return {
            k: (v.decode() if isinstance(v, bytes) else v)
            for k, v in zip(SERVICE_KEYS, values)
        }
    except Exception:  # noqa: BLE001
        return {k: None for k in SERVICE_KEYS}


async def _touch_last_ok(keys: List[str]) -> None:
    if not keys:
        return
    try:
        client = aioredis.from_url(str(settings.REDIS_URL), socket_connect_timeout=2)
        try:
            pipe = client.pipeline()
            for key in keys:
                pipe.set(f"health:last_ok:{key}", _now(), ex=14 * 24 * 3600)
            await pipe.execute()
        finally:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass


LABELS = {
    "postgres": "PostgreSQL",
    "redis": "Redis",
    "celery": "Celery (фоновые задачи)",
    "gateway": "Шлюз интеграций",
    "avito": "Авито",
    "telegram": "Telegram-бот",
    "email": "Почта (SMTP)",
}


@router.get("")
async def health_check():
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check():
    return {"status": "ready"}


@router.get("/services")
async def services_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Живость всех сервисов: postgres, redis, celery, шлюз, Авито, Telegram, почта.

    last_ok_at — когда сервис последний раз отвечал (из redis), чтобы видеть,
    как долго он лежит.
    """
    now = time.monotonic()
    if _cache["data"] and now - _cache["at"] < CACHE_TTL:
        return _cache["data"]

    (pg, rd, celery_res, (gw, gw_status), email) = await asyncio.gather(
        _check_postgres(db),
        _check_redis(),
        _check_celery(),
        _check_gateway(),
        _check_email(db),
    )

    checks = {
        "postgres": pg,
        "redis": rd,
        "celery": celery_res,
        "gateway": gw,
        "avito": _check_avito(gw_status),
        "telegram": _check_telegram(gw_status),
        "email": email,
    }

    await _touch_last_ok([k for k, v in checks.items() if v["status"] == "ok"])
    last_ok = await _last_ok_map()

    services: List[dict] = [
        {
            "key": key,
            "label": LABELS[key],
            "status": checks[key]["status"],
            "detail": checks[key].get("detail"),
            "last_ok_at": last_ok.get(key),
        }
        for key in SERVICE_KEYS
    ]

    data = {"services": services, "checked_at": _now()}
    _cache.update(at=now, data=data)
    return data

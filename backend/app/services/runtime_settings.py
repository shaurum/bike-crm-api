"""Ключи и токены, которые админ задаёт в настройках поверх .env.

Значения хранятся в integration_setting под именем «runtime»: обычные в config,
секретные в secret. Значение из настроек главнее .env, пустое — значит «берём из .env».

Читать их нужно и из синхронного кода (celery, settings.X), поэтому кэш процесса
обновляется синхронно раз в CACHE_TTL секунд: запрос к БД идёт в отдельном потоке
со своим event loop и одноразовым соединением. Другие процессы (воркеры gunicorn,
celery) увидят новое значение не позже чем через CACHE_TTL.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

STORAGE_NAME = "runtime"
STORAGE_TITLE = "Ключи и токены"
CACHE_TTL = 30.0
LOAD_TIMEOUT = 5.0


@dataclass(frozen=True)
class RuntimeKey:
    name: str
    label: str
    group: str
    secret: bool
    help: str
    url: bool = False


KEYS: tuple[RuntimeKey, ...] = (
    RuntimeKey(
        "GDEGAZEL_API_TOKEN",
        "API-токен GDEGAZEL",
        "GPS-трекеры",
        True,
        "Приложение мониторинга GDEGAZEL, меню «API» → «API-токен»",
    ),
    RuntimeKey(
        "GATEWAY_URL",
        "Адрес облачного шлюза",
        "Облачный шлюз (Авито и Telegram)",
        False,
        "Например https://gateway.example.com, без / на конце",
        url=True,
    ),
    RuntimeKey(
        "GATEWAY_TOKEN",
        "Токен облачного шлюза",
        "Облачный шлюз (Авито и Telegram)",
        True,
        "Выдаётся при настройке шлюза",
    ),
    RuntimeKey(
        "TELEGRAM_BOT_TOKEN",
        "Токен Telegram-бота для уведомлений",
        "Telegram",
        True,
        "Выдаёт @BotFather; нужен для уведомлений сотрудникам напрямую, без шлюза",
    ),
    RuntimeKey(
        "PUBLIC_BASE_URL",
        "Публичный адрес сайта",
        "Сайт",
        False,
        "По нему шлюз скачивает вложения из CRM, например https://crm.example.com",
        url=True,
    ),
    RuntimeKey(
        "PUBLIC_API_KEY",
        "Ключ публичного API (виджет на сайте)",
        "Сайт",
        True,
        "Передаётся виджетом заявок в заголовке X-API-Key",
    ),
)

KEYS_BY_NAME = {key.name: key for key in KEYS}

_cache: dict = {"at": float("-inf"), "values": {}}
_lock = threading.Lock()
_local = threading.local()


def _split(config: Optional[dict], secret: Optional[dict]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in KEYS:
        source = secret if key.secret else config
        raw = (source or {}).get(key.name)
        if isinstance(raw, str) and raw.strip():
            values[key.name] = raw.strip()
    return values


async def _fetch() -> dict[str, str]:
    # Импорты здесь: config импортирует этот модуль, цикл на уровне модуля недопустим
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.models import IntegrationSetting

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    select(IntegrationSetting.config, IntegrationSetting.secret).where(
                        IntegrationSetting.name == STORAGE_NAME
                    )
                )
            ).first()
    finally:
        await engine.dispose()
    return _split(row[0], row[1]) if row else {}


def _run_fetch() -> dict[str, str]:
    # Если импорт моделей в этом потоке прочитает settings.X, ждать _lock нельзя: он у вызвавшего
    _local.loading = True
    return asyncio.run(_fetch())


def _load() -> dict[str, str]:
    # Свой поток со своим loop: работает и из синхронного кода, и внутри запущенного loop
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_run_fetch).result(timeout=LOAD_TIMEOUT)


def overrides() -> dict[str, str]:
    """Значения из настроек; при сбое БД остаются прежние, а .env продолжает работать."""
    if getattr(_local, "loading", False):
        return {}
    now = time.monotonic()
    if now - _cache["at"] < CACHE_TTL:
        return _cache["values"]
    with _lock:
        if time.monotonic() - _cache["at"] < CACHE_TTL:
            return _cache["values"]
        try:
            _cache["values"] = _load()
        except Exception as exc:  # noqa: BLE001
            # Таблицы может не быть до миграций, а БД — во время рестарта
            logger.warning("Ключи из настроек не загружены: %s", type(exc).__name__)
        _cache["at"] = time.monotonic()
        return _cache["values"]


def override(name: str) -> Optional[str]:
    return overrides().get(name)


def env_value(name: str) -> str:
    """Значение из .env (или значение поля Settings по умолчанию) без учёта настроек."""
    from app.core.config import RUNTIME_OVERRIDABLE, settings

    if name in RUNTIME_OVERRIDABLE:
        raw = object.__getattribute__(settings, name)
    else:
        raw = os.environ.get(name)
    return str(raw).strip() if raw else ""


def is_default(name: str) -> bool:
    """Значение не задано ни в настройках, ни в окружении, работает умолчание из кода."""
    from app.core.config import RUNTIME_OVERRIDABLE, Settings

    if name not in RUNTIME_OVERRIDABLE or override(name) or os.environ.get(name):
        return False
    default = Settings.model_fields[name].default
    return bool(default) and env_value(name) == str(default)


def get(name: str) -> str:
    """Значение ключа: из настроек, иначе из окружения (.env)."""
    return override(name) or env_value(name)


def remember(config: Optional[dict], secret: Optional[dict]) -> None:
    """Сразу после сохранения: этот процесс не ждёт истечения кэша."""
    with _lock:
        _cache["values"] = _split(config, secret)
        _cache["at"] = time.monotonic()


def reset_cache() -> None:
    with _lock:
        _cache["values"] = {}
        _cache["at"] = float("-inf")

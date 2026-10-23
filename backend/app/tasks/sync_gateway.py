"""Забирает события с облачного шлюза и кладёт их в чати CRM."""

import asyncio
import json
import logging

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import IntegrationSetting
from app.services import gateway

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

NAME = "gateway"
BATCH = 100
MAX_SKIPPED = 100
WARN_EVERY = 300.0

_last_warning: tuple = (0.0, "")


def _warn(message: str) -> None:
    """Повторяющуюся ошибку пишем редко: задача крутится каждые 10 секунд."""
    global _last_warning
    import time

    moment, previous = _last_warning
    if message == previous and time.monotonic() - moment < WARN_EVERY:
        return
    _last_warning = (time.monotonic(), message)
    logger.warning("%s", message)


async def _load(session: AsyncSession) -> IntegrationSetting:
    result = await session.execute(
        select(IntegrationSetting).where(IntegrationSetting.name == NAME)
    )
    item = result.scalar_one_or_none()
    if not item:
        item = IntegrationSetting(
            name=NAME, title="Облачный шлюз", is_enabled=True, config={}, secret={}
        )
        session.add(item)
        await session.flush()
    return item


async def _resolve_attachments(session: AsyncSession, raw) -> list[dict]:
    """Описания медиа со шлюза: URL остаются, file_id скачиваем в uploads."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = []
    if not isinstance(raw, list):
        return []

    out: list[dict] = []
    token: str | None = None
    for item in raw:
        if isinstance(item, str):
            item = {"url": item}
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if url:
            out.append(
                {
                    "url": url,
                    **({"name": item["name"]} if item.get("name") else {}),
                    **(
                        {"content_type": item["content_type"]}
                        if item.get("content_type")
                        else {}
                    ),
                }
            )
            continue
        file_id = str(item.get("file_id") or "").strip()
        if not file_id:
            continue
        if token is None:
            from app.tasks.webhooks import _telegram_token

            token = await _telegram_token(session)
        if not token:
            continue
        from app.services.tg_media import save_tg_file

        saved = await save_tg_file(token, file_id, name=item.get("name"))
        if saved:
            out.append(saved)
    return out


async def _ingest_event(session: AsyncSession, event: dict) -> None:
    from app.tasks.webhooks import _ingest

    source = str(event.get("source") or "")
    text = str(event.get("text") or "").strip()
    attachments = await _resolve_attachments(
        session, event.get("media") or event.get("attachments")
    )
    if not text and not attachments:
        return
    if not text:
        text = "Вложение"
    if source not in ("avito", "telegram"):
        logger.info("Шлюз: источник «%s» пока не поддержан, событие пропущено", source)
        return

    chat_id = str(event.get("chat_id") or "")
    # Ник важнее числового id: иначе входящее не находит клиента, добавленного по @username
    username = str(event.get("username") or "").strip().lstrip("@")
    await _ingest(
        session,
        channel=source,
        sender=str(username or event.get("sender") or chat_id),
        content=text,
        name=event.get("sender_name"),
        msg_id=str(event.get("external_id") or "") or None,
        external_id=chat_id or None,
        attachments=attachments,
        meta={
            "chat_id": chat_id,
            "gateway_event_id": event.get("id"),
            **({"tg_user_id": event.get("sender")} if event.get("sender") else {}),
        },
    )


async def _sync() -> None:
    if not gateway.is_configured():
        return

    async with async_session_maker() as session:
        item = await _load(session)
        config = dict(item.config or {})
        cursor = int(config.get("cursor") or 0)
        skipped = set(str(x) for x in (config.get("skipped") or []))
        await session.commit()

        try:
            payload = await gateway.pull_events(after=cursor, limit=BATCH)
        except gateway.GatewayError as exc:
            _warn(f"Шлюз: события не забраны: {exc}")
            return

        events = payload.get("events") or []
        if not events:
            return

        last = cursor
        newly_skipped: list[str] = []

        for event in events:
            event_id = int(event.get("id") or 0)
            external_id = str(event.get("external_id") or "")
            last = max(last, event_id)

            if external_id and external_id in skipped:
                continue

            try:
                await _ingest_event(session, event)
                await session.commit()
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                logger.exception(
                    "Шлюз: не разобрали событие id=%s: %s", event_id, exc
                )
                if external_id:
                    newly_skipped.append(external_id)

        if last == cursor and not newly_skipped:
            return

        fresh = await _load(session)
        config = dict(fresh.config or {})
        config["cursor"] = last
        if newly_skipped:
            merged = [str(x) for x in (config.get("skipped") or [])] + newly_skipped
            config["skipped"] = merged[-MAX_SKIPPED:]
        fresh.config = config
        await session.commit()

        logger.info(
            "Шлюз: забрано %s событий (курсор %s -> %s, отложено %s)",
            len(events),
            cursor,
            last,
            len(newly_skipped),
        )


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def sync_gateway_events(self):
    asyncio.run(_sync())

import logging
from typing import Optional
from datetime import datetime, timezone
from uuid import UUID

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import Lead
from app.services.messaging import DuplicateMessage, ingest_inbound

logger = logging.getLogger(__name__)

engine = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool
    )
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_avito_webhook(self, source_id: str, payload: dict):
    import asyncio
    asyncio.run(_process_avito_webhook(source_id, payload))


async def _process_avito_webhook(source_id: str, payload: dict):
    """Сообщения из Авито: кладём в чат клиента."""
    async with async_session_maker() as session:
        try:
            chat = payload.get("chat", {})
            user = chat.get("user", {})
            messages = payload.get("messages", [])
            if not messages:
                return

            name = user.get("name")
            sender = user.get("phone") or user.get("email") or str(chat.get("id", ""))
            if not sender:
                logger.warning("No sender in Avito payload")
                return

            lead = await _get_lead(session, source_id, str(chat.get("id", "")))
            for msg in messages:
                msg_id = str(msg.get("id", ""))
                if not msg_id:
                    continue
                await _ingest(
                    session,
                    channel="avito",
                    sender=sender,
                    content=msg.get("content", {}).get("text", ""),
                    name=name,
                    phone=user.get("phone"),
                    email=user.get("email"),
                    msg_id=msg_id,
                    external_id=str(chat.get("id", "")) or None,
                    meta={"author": msg.get("author", {}), "source_id": source_id},
                    subject=None,
                )
            if lead:
                lead.raw_payload = payload
                lead.updated_at = datetime.now(timezone.utc)
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception("Error processing Avito webhook: %s", e)
            raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_vk_webhook(self, source_id: str, payload: dict):
    import asyncio
    asyncio.run(_process_vk_webhook(source_id, payload))


async def _process_vk_webhook(source_id: str, payload: dict):
    if payload.get("type") != "message_new":
        return

    async with async_session_maker() as session:
        try:
            msg = payload.get("object", {}).get("message", {})
            from_id = str(msg.get("from_id", ""))
            text = msg.get("text", "")
            if not from_id or not text:
                return

            await _ingest(
                session,
                channel="vk",
                sender=from_id,
                content=text,
                name=None,
                msg_id=str(msg.get("id", "")),
                meta={"from_id": from_id, "source_id": source_id},
                subject=None,
            )
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception("Error processing VK webhook: %s", e)
            raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_telegram_webhook(self, source_id: str, payload: dict):
    import asyncio
    asyncio.run(_process_telegram_webhook(source_id, payload))


async def _process_telegram_webhook(source_id: str, payload: dict):
    async with async_session_maker() as session:
        try:
            message = payload.get("message", {})
            chat = message.get("chat", {})
            chat_id = str(chat.get("id", ""))
            text = message.get("text", "")
            from_user = message.get("from", {})
            if not chat_id or not text:
                return

            name = (
                f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip()
                or None
            )
            sender = from_user.get("username") or chat_id
            if not sender:
                return

            await _ingest(
                session,
                channel="telegram",
                sender=sender,
                content=text,
                name=name,
                msg_id=str(message.get("message_id", "")),
                meta={"from": from_user, "chat": chat, "source_id": source_id},
                subject=None,
            )
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception("Error processing Telegram webhook: %s", e)
            raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_email_webhook(self, source_id: str, payload: dict):
    import asyncio
    asyncio.run(_process_email_webhook(source_id, payload))


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def poll_email_inbox(self):
    """Забираем входящие письма по IMAP и кладём в чаты клиентов."""
    import asyncio
    asyncio.run(_poll_email_inbox())


async def _poll_email_inbox():
    from starlette.concurrency import run_in_threadpool

    from app.services.email_inbox import (
        ImapError,
        fetch_new_emails,
        get_imap_settings,
        parse_email,
    )

    async with async_session_maker() as session:
        imap_settings = await get_imap_settings(session)
        if not imap_settings:
            return
        if not imap_settings.is_ready:
            logger.info("IMAP не настроен, пропускаем опрос входящих")
            return

        try:
            items = await run_in_threadpool(fetch_new_emails, imap_settings)
        except ImapError as exc:
            logger.warning("IMAP: %s", exc)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("IMAP: ошибка опроса: %s", exc)
            return

        if not items:
            return

        max_uid = imap_settings.last_uid
        processed = 0

        for item in items:
            uid = item["uid"]
            try:
                payload = parse_email(uid, item["msg"])
                if not payload["sender_value"]:
                    logger.info("IMAP: пропускаем письмо без отправителя, uid=%s", uid)
                    continue
                await _ingest(
                    session,
                    channel="email",
                    sender=payload["sender_value"],
                    content=payload["content"],
                    name=payload["sender_name"],
                    msg_id=payload["external_msg_id"],
                    meta=payload["meta"],
                    subject=payload["subject"],
                )
                max_uid = max(max_uid, uid)
                processed += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("IMAP: не разобрали письмо uid=%s: %s", uid, exc)

        # Запоминаем прогресс только после успешной обработки
        if max_uid > imap_settings.last_uid:
            await _store_last_uid(session, max_uid)

        if processed:
            logger.info("IMAP: обработано писем: %s", processed)


async def _store_last_uid(session, uid: int) -> None:
    from app.models import IntegrationSetting

    result = await session.execute(
        select(IntegrationSetting).where(IntegrationSetting.name == "email")
    )
    item = result.scalars().first()
    if not item:
        return
    config = dict(item.config or {})
    config["imap_last_uid"] = uid
    item.config = config
    await session.commit()


async def _process_email_webhook(source_id: str, payload: dict):
    """Письмо превращается в чат с клиентом."""
    async with async_session_maker() as session:
        try:
            email_id = payload.get("Message-ID") or payload.get("message_id")
            if not email_id:
                return

            sender = payload.get("from", {}) or {}
            address = sender.get("email") if isinstance(sender, dict) else str(sender)
            if not address:
                logger.warning("No sender address in email payload")
                return

            content = payload.get("text", "") or (payload.get("html") or "")[:2000]

            await _ingest(
                session,
                channel="email",
                sender=address,
                content=content,
                name=sender.get("name") if isinstance(sender, dict) else None,
                msg_id=email_id,
                meta={"subject": payload.get("subject"), "from": sender, "source_id": source_id},
                subject=payload.get("subject"),
            )
            await session.commit()
        except DuplicateMessage as exc:
            # Письмо уже доставлено — не считаем это ошибкой
            await session.rollback()
            logger.info("Email already processed: %s", exc.external_msg_id)
        except Exception as e:
            await session.rollback()
            logger.exception("Error processing Email webhook: %s", e)
            raise


async def _get_lead(session: AsyncSession, source_id: str, external_id: str):
    """Существующий лид по внешнему ID (для обновления payload)."""
    result = await session.execute(
        select(Lead).where(Lead.source_id == UUID(source_id), Lead.external_id == external_id)
    )
    return result.scalar_one_or_none()


async def _ingest(
    session: AsyncSession,
    *,
    channel: str,
    sender: str,
    content: str,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    msg_id: str | None = None,
    external_id: str | None = None,
    meta: dict | None = None,
    subject: str | None = None,
):
    """Единая точка входа для всех каналов.

    Создаёт клиента, чат и лид, если это нужно, и кладёт сообщение туда.
    """
    try:
        result = await ingest_inbound(
            session,
            channel=channel,
            sender_value=sender,
            content=content,
            sender_name=name,
            subject=subject,
            external_msg_id=msg_id,
            external_id=external_id,
            phone=phone,
            email=email,
            meta=meta,
        )
    except DuplicateMessage as exc:
        logger.info("Duplicate %s message skipped: %s", channel, exc.external_msg_id)
        return None

    if result.created_lead:
        await _notify_managers_new_lead(result.lead, session)

    logger.info(
        "Inbound %s -> customer %s, lead %s (created=%s)",
        channel,
        result.customer.id,
        result.lead.id,
        result.created_lead,
    )
    return result


async def _notify_managers_new_lead(lead: Lead, session: AsyncSession):
    from app.models import User
    from app.tasks.notifications import send_telegram_notification

    result = await session.execute(
        select(User).where(
            User.role == "admin", User.is_active == True, User.telegram_chat_id.isnot(None)  # noqa: E712
        )
    )
    admins = result.scalars().all()

    for admin in admins:
        send_telegram_notification.delay(
            admin.telegram_chat_id,
            "Новый лид!\n"
            f"Клиент: {lead.client_name}\n"
            f"Телефон: {lead.client_phone or '—'}\n"
            f"Почта: {lead.client_email or '—'}",
        )


@shared_task
def refresh_avito_tokens():
    """Продлеваем токен Авито: он живёт 24 часа."""
    import asyncio

    asyncio.run(_refresh_avito_tokens())


async def _refresh_avito_tokens():
    from app.services import gateway
    from app.services.avito import AvitoError, load_integration, refresh_access_token

    if gateway.is_configured():
        # Токенами Авито управляет шлюз — локально не мешаем
        return

    async with async_session_maker() as session:
        try:
            item = await load_integration(session)
        except AvitoError:
            return
        if not (item.secret or {}).get("refresh_token"):
            return
        try:
            await refresh_access_token(session, item)
        except AvitoError as exc:
            logger.warning("Avito: не удалось обновить токен: %s", exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def poll_avito_messages(self):
    """Забираем входящие сообщения из Авито в чаты клиентов."""
    import asyncio

    asyncio.run(_poll_avito_messages())


async def _poll_avito_messages():
    from app.services import gateway
    from app.services.avito import (
        AvitoError,
        account_user_id,
        counterparty_id,
        counterparty_name,
        list_chats,
        list_messages,
        load_integration,
        message_text,
    )

    if gateway.is_configured():
        # Опрос Авито выполняет шлюз, здесь забираем уже готовые события
        return

    async with async_session_maker() as session:
        try:
            item = await load_integration(session)
        except AvitoError:
            return
        if not (item.secret or {}).get("access_token"):
            return

        try:
            user_id = account_user_id(item)
            chats = await list_chats(session, user_id)
        except AvitoError as exc:
            logger.warning("Avito: опрос чатов не удался: %s", exc)
            return

        if not chats:
            return

        seen = dict((item.config or {}).get("avito_seen") or {})
        updates: dict[str, int] = {}

        for chat in chats:
            chat_id = str(chat.get("id") or "")
            if not chat_id:
                continue
            last = chat.get("last_message") or {}
            if str(last.get("direction") or "") != "in":
                continue
            created = int(last.get("created") or 0)
            if created <= int(seen.get(chat_id) or 0):
                continue

            try:
                items = await list_messages(session, user_id, chat_id, limit=50)
            except AvitoError as exc:
                logger.warning("Avito: чат %s не прочитан: %s", chat_id, exc)
                continue

            sender = counterparty_id(chat, user_id) or chat_id
            name = counterparty_name(chat, user_id)
            highest = created
            failed = False

            for msg in items:
                if str(msg.get("direction") or "") != "in":
                    continue
                msg_id = str(msg.get("id") or "")
                text = message_text(msg)
                if not msg_id or not text:
                    continue
                try:
                    await _ingest(
                        session,
                        channel="avito",
                        sender=sender,
                        content=text,
                        name=name,
                        msg_id=msg_id,
                        external_id=chat_id,
                        meta={"chat_id": chat_id, "author_id": msg.get("author_id")},
                    )
                    await session.commit()
                except Exception as exc:  # noqa: BLE001
                    await session.rollback()
                    logger.exception("Avito: не разобрали сообщение %s: %s", msg_id, exc)
                    failed = True
                highest = max(highest, int(msg.get("created") or 0))

            if not failed:
                updates[chat_id] = max(highest, created)

        if not updates:
            return

        try:
            fresh = await load_integration(session)
        except AvitoError:
            return
        config = dict(fresh.config or {})
        seen = dict(config.get("avito_seen") or {})
        seen.update(updates)
        config["avito_seen"] = seen
        fresh.config = config
        await session.commit()

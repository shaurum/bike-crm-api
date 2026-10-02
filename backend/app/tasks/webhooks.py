import logging
from celery import shared_task
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timezone

from app.core.config import settings
from app.models import Lead, LeadSource, LeadStatus, LeadMessage, PipelineStage

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
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


def get_default_stage(session: AsyncSession) -> PipelineStage:
    result = session.execute(select(PipelineStage).where(PipelineStage.is_default == True))
    stage = result.scalar_one_or_none()
    if not stage:
        stage = PipelineStage(name="Новый", order=0, color="#3B82F6", is_default=True)
        session.add(stage)
        session.flush()
    return stage


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_avito_webhook(self, source_id: str, payload: dict):
    import asyncio
    asyncio.run(_process_avito_webhook(source_id, payload))


async def _process_avito_webhook(source_id: str, payload: dict):
    async with async_session_maker() as session:
        try:
            source = await session.get(LeadSource, UUID(source_id))
            if not source:
                logger.error(f"Source {source_id} not found")
                return

            chat = payload.get("chat", {})
            user = chat.get("user", {})
            messages = payload.get("messages", [])

            external_id = str(chat.get("id", ""))
            if not external_id:
                logger.warning("No chat ID in Avito payload")
                return

            result = await session.execute(
                select(Lead).where(Lead.source_id == source.id, Lead.external_id == external_id)
            )
            lead = result.scalar_one_or_none()

            if not lead:
                default_stage = get_default_stage(session)
                lead = Lead(
                    source_id=source.id,
                    external_id=external_id,
                    raw_payload=payload,
                    client_name=user.get("name"),
                    client_phone=user.get("phone"),
                    client_email=user.get("email"),
                    status=LeadStatus.NEW,
                    stage_id=default_stage.id,
                    initial_message=messages[0].get("content", {}).get("text") if messages else None,
                )
                session.add(lead)
                await session.flush()

                await _notify_managers_new_lead(lead, session)
            else:
                lead.raw_payload = payload
                lead.updated_at = datetime.now(timezone.utc)

            for msg in messages:
                msg_id = str(msg.get("id", ""))
                if not msg_id:
                    continue
                existing = await session.execute(
                    select(LeadMessage).where(LeadMessage.external_msg_id == msg_id)
                )
                if existing.scalar_one_or_none():
                    continue

                direction = "inbound" if msg.get("direction") == "in" else "outbound"
                lead_message = LeadMessage(
                    lead_id=lead.id,
                    channel="avito",
                    direction=direction,
                    content=msg.get("content", {}).get("text", ""),
                    external_msg_id=msg_id,
                    meta={"author": msg.get("author", {})},
                )
                session.add(lead_message)

            await session.commit()
            logger.info(f"Processed Avito webhook for lead {lead.id}")

        except Exception as e:
            await session.rollback()
            logger.exception(f"Error processing Avito webhook: {e}")
            raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_vk_webhook(self, source_id: str, payload: dict):
    import asyncio
    asyncio.run(_process_vk_webhook(source_id, payload))


async def _process_vk_webhook(source_id: str, payload: dict):
    async with async_session_maker() as session:
        try:
            if payload.get("type") == "message_new":
                msg = payload.get("object", {}).get("message", {})
                external_id = str(msg.get("peer_id", ""))
                from_id = str(msg.get("from_id", ""))
                text = msg.get("text", "")

                result = await session.execute(
                    select(Lead).where(Lead.source_id == UUID(source_id), Lead.external_id == external_id)
                )
                lead = result.scalar_one_or_none()

                if not lead:
                    default_stage = get_default_stage(session)
                    lead = Lead(
                        source_id=UUID(source_id),
                        external_id=external_id,
                        raw_payload=payload,
                        client_phone=from_id,
                        status=LeadStatus.NEW,
                        stage_id=default_stage.id,
                        initial_message=text,
                    )
                    session.add(lead)
                    await session.flush()
                    await _notify_managers_new_lead(lead, session)

                lead_message = LeadMessage(
                    lead_id=lead.id,
                    channel="vk",
                    direction="inbound",
                    content=text,
                    external_msg_id=str(msg.get("id", "")),
                    meta={"from_id": from_id},
                )
                session.add(lead_message)

                await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception(f"Error processing VK webhook: {e}")
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

            result = await session.execute(
                select(Lead).where(Lead.source_id == UUID(source_id), Lead.external_id == chat_id)
            )
            lead = result.scalar_one_or_none()

            if not lead:
                default_stage = get_default_stage(session)
                lead = Lead(
                    source_id=UUID(source_id),
                    external_id=chat_id,
                    raw_payload=payload,
                    client_name=f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip(),
                    client_phone=from_user.get("username"),
                    status=LeadStatus.NEW,
                    stage_id=default_stage.id,
                    initial_message=text,
                )
                session.add(lead)
                await session.flush()
                await _notify_managers_new_lead(lead, session)

            lead_message = LeadMessage(
                lead_id=lead.id,
                channel="telegram",
                direction="inbound",
                content=text,
                external_msg_id=str(message.get("message_id", "")),
                meta={"from": from_user, "chat": chat},
            )
            session.add(lead_message)

            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception(f"Error processing Telegram webhook: {e}")
            raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_email_webhook(self, source_id: str, payload: dict):
    import asyncio
    asyncio.run(_process_email_webhook(source_id, payload))


async def _process_email_webhook(source_id: str, payload: dict):
    async with async_session_maker() as session:
        try:
            email_id = payload.get("Message-ID") or payload.get("message_id")
            if not email_id:
                return

            result = await session.execute(
                select(Lead).where(Lead.source_id == UUID(source_id), Lead.external_id == email_id)
            )
            lead = result.scalar_one_or_none()

            if not lead:
                default_stage = get_default_stage(session)
                lead = Lead(
                    source_id=UUID(source_id),
                    external_id=email_id,
                    raw_payload=payload,
                    client_name=payload.get("from", {}).get("name"),
                    client_email=payload.get("from", {}).get("email"),
                    status=LeadStatus.NEW,
                    stage_id=default_stage.id,
                    initial_message=payload.get("subject", ""),
                )
                session.add(lead)
                await session.flush()
                await _notify_managers_new_lead(lead, session)

            lead_message = LeadMessage(
                lead_id=lead.id,
                channel="email",
                direction="inbound",
                content=payload.get("text", "") or payload.get("html", "")[:2000],
                external_msg_id=email_id,
                meta={"subject": payload.get("subject"), "from": payload.get("from")},
            )
            session.add(lead_message)

            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception(f"Error processing Email webhook: {e}")
            raise


async def _notify_managers_new_lead(lead: Lead, session: AsyncSession):
    from app.models import User
    result = await session.execute(
        select(User).where(User.role == "admin", User.is_active == True, User.telegram_chat_id.isnot(None))
    )
    admins = result.scalars().all()

    for admin in admins:
        from app.tasks.notifications import send_telegram_notification
        send_telegram_notification.delay(
            admin.telegram_chat_id,
            f"🔔 Новый лид!\nИсточник: {lead.source.type.value}\nКлиент: {lead.client_name}\nТелефон: {lead.client_phone}",
        )


@shared_task
def refresh_avito_tokens():
    logger.info("Checking Avito tokens refresh...")
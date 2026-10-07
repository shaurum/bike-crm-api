"""Обработка входящих сообщений.

Правила:
1. Ищем контакт по каналу и адресу отправителя.
2. Если не нашли — создаём клиента и заполняем что есть.
3. Если у клиента есть активная сделка — сообщение летит в существующий чат.
4. Если нет — создаётся новый лид, чат продолжается там же.
5. Повторное сообщение с тем же external_msg_id игнорируется.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ContactPoint,
    Conversation,
    Customer,
    Lead,
    LeadMessage,
    LeadSource,
    LeadSourceType,
    LeadStatus,
)
from app.models.crm import PipelineStage

logger = logging.getLogger(__name__)

# Статусы, которые считаем «сделка открыта»
ACTIVE_STATUSES = (
    LeadStatus.NEW,
    LeadStatus.CONTACTED,
    LeadStatus.QUALIFIED,
    LeadStatus.BOOKING,
)

# Канал -> тип источника для авто-создания лида
CHANNEL_TO_SOURCE = {
    "email": LeadSourceType.EMAIL,
    "telegram": LeadSourceType.TELEGRAM,
    "vk": LeadSourceType.VK,
    "avito": LeadSourceType.AVITO,
    "widget": LeadSourceType.WIDGET,
}


@dataclass
class IngestResult:
    """Итог обработки входящего сообщения."""

    conversation: Conversation
    lead: Optional[Lead]
    customer: Customer
    created_lead: bool
    created_customer: bool
    message: LeadMessage
    duplicate: bool = False


def normalize_value(channel: str, value: str) -> str:
    """Нормализуем адрес, чтобы один и тот же собеседник находился всегда."""
    raw = (value or "").strip().lower()
    if channel == "email":
        return raw
    if channel == "phone":
        return "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    if channel == "telegram":
        return raw.lstrip("@")
    return raw


async def _find_contact(db: AsyncSession, channel: str, value: str):
    result = await db.execute(
        select(ContactPoint).where(
            ContactPoint.channel == channel,
            ContactPoint.value == value,
        )
    )
    return result.scalars().first()


async def _find_customer(
    db: AsyncSession,
    channel: str,
    value: str,
    email: Optional[str],
    phone: Optional[str],
):
    """Ищем клиента по контактам. Важно: ищем и по позапрошлому каналу."""
    contact = await _find_contact(db, channel, value)
    if contact:
        return await db.get(Customer, contact.customer_id)

    # Клиент мог прийти раньше другим способом связи — ищем по другим каналам
    for ch, val in (("email", email), ("phone", phone)):
        if not val or not val.strip():
            continue
        found = await _find_contact(db, ch, val.strip().lower())
        if found:
            return await db.get(Customer, found.customer_id)

    return None


async def _get_source(db: AsyncSession, channel: str) -> LeadSource:
    """Находим или создаём источник для канала."""
    source_type = CHANNEL_TO_SOURCE.get(channel, LeadSourceType.MANUAL)
    result = await db.execute(
        select(LeadSource).where(
            LeadSource.type == source_type,
            LeadSource.is_active == True,  # noqa: E712
        )
    )
    source = result.scalars().first()
    if source:
        return source

    source = LeadSource(type=source_type, name=channel.title(), config={}, is_active=True)
    db.add(source)
    await db.flush()
    return source


async def _get_default_stage(db: AsyncSession) -> Optional[uuid.UUID]:
    result = await db.execute(
        select(PipelineStage).where(PipelineStage.is_default == True)  # noqa: E712
    )
    stage = result.scalars().first()
    return stage.id if stage else None


async def _find_active_lead(db: AsyncSession, customer_id: uuid.UUID) -> Optional[Lead]:
    """Открытая сделка клиента — если она есть, чат уже «в воронке»."""
    result = await db.execute(
        select(Lead).where(
            Lead.customer_id == customer_id,
            Lead.status.in_(ACTIVE_STATUSES),
        ).order_by(Lead.created_at.desc())
    )
    return result.scalars().first()


async def ingest_inbound(
    db: AsyncSession,
    *,
    channel: str,
    sender_value: str,
    content: str,
    sender_name: Optional[str] = None,
    subject: Optional[str] = None,
    external_msg_id: Optional[str] = None,
    external_id: Optional[str] = None,
    meta: Optional[dict] = None,
) -> IngestResult:
    """Принимает входящее сообщение и кладёт его в правильный чат."""
    value = normalize_value(channel, sender_value)

    # Повторная доставка того же сообщения — игнорируем
    if external_msg_id:
        dup = await db.execute(
            select(LeadMessage.id).where(
                LeadMessage.channel == channel,
                LeadMessage.external_msg_id == external_msg_id,
            )
        )
        if dup.first():
            raise DuplicateMessage(external_msg_id)

    email = value if channel == "email" else None
    phone = value if channel == "phone" else None

    customer = await _find_customer(db, channel, value, email=email, phone=phone)
    created_customer = False

    if not customer:
        created_customer = True
        customer = Customer(
            full_name=(sender_name or value or "Без имени").strip() or "Без имени",
            email=email,
            phone=phone,
        )
        db.add(customer)
        await db.flush()

        db.add(
            ContactPoint(
                customer_id=customer.id,
                channel=channel,
                value=value,
                external_id=external_id,
                is_primary=True,
                is_verified=False,
            )
        )
        await db.flush()
    else:
        # Контакт этого канала мог добавиться позже — дописываем
        existing = await _find_contact(db, channel, value)
        if not existing:
            db.add(
                ContactPoint(
                    customer_id=customer.id,
                    channel=channel,
                    value=value,
                    external_id=external_id,
                    is_primary=True,
                    is_verified=False,
                )
            )
            await db.flush()
        elif external_id and not existing.external_id:
            existing.external_id = external_id

    # Чат живёт отдельно от сделки, создаётся один раз на клиента
    result = await db.execute(
        select(Conversation).where(Conversation.customer_id == customer.id)
    )
    conversation = result.scalars().first()
    if not conversation:
        conversation = Conversation(customer_id=customer.id, status="open")
        db.add(conversation)
        await db.flush()

    # Если клиента только что создали или у него нет активной сделки — новый лид
    lead = await _find_active_lead(db, customer.id)
    created_lead = False
    if not lead:
        created_lead = True
        source = await _get_source(db, channel)
        lead = Lead(
            source_id=source.id,
            external_id=external_msg_id or f"auto-{uuid.uuid4().hex}",
            raw_payload=meta or {},
            client_name=sender_name,
            client_phone=phone,
            client_email=email,
            status=LeadStatus.NEW,
            stage_id=await _get_default_stage(db),
            initial_message=(subject or content)[:500],
            customer_id=customer.id,
        )
        db.add(lead)
        await db.flush()
        conversation.lead_id = lead.id
    elif conversation.lead_id != lead.id:
        conversation.lead_id = lead.id

    message = LeadMessage(
        lead_id=lead.id,
        conversation_id=conversation.id,
        channel=channel,
        direction="inbound",
        content=content,
        external_msg_id=external_msg_id,
        meta=meta or {},
        is_read=False,
    )
    db.add(message)

    conversation.last_message_at = message.created_at or _now()
    conversation.unread_count = (conversation.unread_count or 0) + 1

    await db.flush()

    return IngestResult(
        conversation=conversation,
        lead=lead,
        customer=customer,
        created_lead=created_lead,
        created_customer=created_customer,
        message=message,
    )


class DuplicateMessage(Exception):
    """Сообщение с таким external_msg_id уже обработано."""

    def __init__(self, external_msg_id: str):
        super().__init__(external_msg_id)
        self.external_msg_id = external_msg_id


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)

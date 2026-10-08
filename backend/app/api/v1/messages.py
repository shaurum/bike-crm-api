"""Раздел «Сообщения»: список диалогов, история, отправка."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models import (
    ContactPoint,
    Conversation,
    Customer,
    Lead,
    LeadMessage,
    LeadStatus,
    User,
)
from app.schemas.messaging import (
    ContactPointCreate,
    ContactPointResponse,
    ContactPointUpdate,
    ConversationDetailResponse,
    ConversationListResponse,
    MessageCreate,
    MessageResponse,
    MessageSendResponse,
)
from app.services.messaging import normalize_value

router = APIRouter()

ACTIVE_STATUSES = (
    LeadStatus.NEW,
    LeadStatus.CONTACTED,
    LeadStatus.QUALIFIED,
    LeadStatus.BOOKING,
)

# Каналы, которые можно реально отправить, и как называется интеграция
SENDABLE_CHANNELS = {"email", "telegram", "vk", "avito"}


def _deal_state(lead: Optional[Lead]) -> str:
    if not lead:
        return "none"
    return "active" if lead.status in ACTIVE_STATUSES else "deal_closed"


async def _load_customer(db: AsyncSession, customer_id: UUID) -> Customer:
    customer = await db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    return customer


async def _load_conversation(db: AsyncSession, conversation_id: UUID) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    return conversation


@router.get("", response_model=List[ConversationListResponse])
async def list_conversations(
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    archived: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Лента диалогов, отсортирована по последнему сообщению.

    По умолчанию скрытые (архивные) чаты не отдаются — ими управляют
    отдельным параметром archived=true.
    """
    query = (
        select(Conversation)
        .where(Conversation.is_archived == archived)
        .order_by(
            Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc()
        )
    )

    rows = (await db.execute(query)).scalars().all()

    customers = {
        c.id: c
        for c in (
            await db.execute(select(Customer).where(Customer.id.in_([r.customer_id for r in rows] or [None])))
        ).scalars().all()
    }

    # Тянем последние сообщения одним запросом
    last_msgs = await _last_messages(db, [r.id for r in rows])

    out: List[ConversationListResponse] = []
    for conv in rows:
        customer = customers.get(conv.customer_id)
        if not customer:
            continue

        lead = await db.get(Lead, conv.lead_id) if conv.lead_id else None
        state = _deal_state(lead)
        if status_filter == "active" and state != "active":
            continue
        if status_filter == "closed" and state == "active":
            continue

        name = customer.full_name or customer.email or customer.phone or "Без имени"
        contacts = await _contact_values(db, customer.id)
        if search:
            needle = search.strip().lower()
            if needle not in name.lower() and not any(needle in c.lower() for c in contacts):
                continue

        last = last_msgs.get(conv.id)
        out.append(
            ConversationListResponse(
                id=conv.id,
                status=conv.status,
                last_message_at=conv.last_message_at,
                unread_count=conv.unread_count or 0,
                customer_id=conv.customer_id,
                customer_name=name,
                lead_id=conv.lead_id,
                deal_state=state,
                preview=(last.content[:140] if last else None),
                channel=(last.channel if last else None),
                awaiting_reply=bool(last and last.direction == "inbound"),
                contacts=contacts,
                is_archived=conv.is_archived,
            )
        )

    return out


async def _last_messages(db: AsyncSession, conversation_ids):
    if not conversation_ids:
        return {}
    result = await db.execute(
        select(LeadMessage)
        .where(LeadMessage.conversation_id.in_(conversation_ids))
        .order_by(LeadMessage.created_at.desc())
    )
    out = {}
    for msg in result.scalars().all():
        out.setdefault(msg.conversation_id, msg)
    return out


async def _contact_values(db: AsyncSession, customer_id: UUID) -> List[str]:
    result = await db.execute(
        select(ContactPoint).where(ContactPoint.customer_id == customer_id)
    )
    return [f"{c.channel}: {c.value}" for c in result.scalars().all()]


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """История переписки вместе с контактами клиента."""
    conv = await _load_conversation(db, conversation_id)
    customer = await _load_customer(db, conv.customer_id)

    result = await db.execute(
        select(LeadMessage)
        .where(LeadMessage.conversation_id == conv.id)
        .order_by(LeadMessage.created_at.asc())
    )
    messages = result.scalars().all()

    contacts_result = await db.execute(
        select(ContactPoint).where(ContactPoint.customer_id == customer.id)
    )
    contacts = list(contacts_result.scalars().all())

    lead = await db.get(Lead, conv.lead_id) if conv.lead_id else None

    authors = {
        a.id: a.full_name
        for a in (
            await db.execute(
                select(User).where(
                    User.id.in_([m.author_id for m in messages if m.author_id] or [None])
                )
            )
        ).scalars().all()
    }

    out_messages = [
        MessageResponse(
            id=m.id,
            channel=m.channel,
            direction=m.direction,
            content=m.content,
            is_read=m.is_read,
            author_name=authors.get(m.author_id) if m.author_id else None,
            subject=(m.meta or {}).get("subject"),
            created_at=m.created_at,
        )
        for m in messages
    ]

    return ConversationDetailResponse(
        id=conv.id,
        status=conv.status,
        is_archived=conv.is_archived,
        last_message_at=conv.last_message_at,
        unread_count=conv.unread_count or 0,
        customer_id=customer.id,
        customer_name=customer.full_name or "Без имени",
        customer_phone=customer.phone,
        customer_email=customer.email,
        lead_id=conv.lead_id,
        deal_state=_deal_state(lead),
        contacts=[
            ContactPointResponse.model_validate(c, from_attributes=True) for c in contacts
        ],
        messages=out_messages,
        channels=sorted({m.channel for m in messages}),
    )


@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Помечаем все диалоги прочитанными."""
    await db.execute(
        update(Conversation)
        .where(Conversation.unread_count > 0)
        .values(unread_count=0)
    )
    await db.execute(
        update(LeadMessage)
        .where(
            LeadMessage.direction == "inbound",
            LeadMessage.is_read == False,  # noqa: E712
        )
        .values(is_read=True)
    )
    await db.commit()
    return {"ok": True}


@router.post("/{conversation_id}/read")
async def mark_read(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Помечаем входящие как прочитанные, сбрасываем счётчик."""
    conv = await _load_conversation(db, conversation_id)

    result = await db.execute(
        select(LeadMessage).where(
            LeadMessage.conversation_id == conv.id,
            LeadMessage.direction == "inbound",
            LeadMessage.is_read == False,  # noqa: E712
        )
    )
    for msg in result.scalars().all():
        msg.is_read = True

    conv.unread_count = 0
    await db.commit()

    return {"ok": True, "unread_count": 0}


@router.post("/{conversation_id}/messages", response_model=MessageSendResponse)
async def send_message(
    conversation_id: UUID,
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отправка в выбранный канал.

    Если канал не подключён, сообщение сохраняется в истории с пометкой
    о том, что отправка не состоялась — так менеджер видит, что ответ не ушёл.
    """
    conv = await _load_conversation(db, conversation_id)
    customer = await _load_customer(db, conv.customer_id)

    channel = payload.channel

    if channel not in SENDABLE_CHANNELS:
        raise HTTPException(
            status_code=400,
            detail=f"Отправлять в канал «{channel}» пока нельзя",
        )

    # Определяем адрес: явный контакт или основной канал
    recipient = None
    if payload.contact_id:
        contact = await db.get(ContactPoint, payload.contact_id)
        if not contact or contact.customer_id != customer.id:
            raise HTTPException(status_code=404, detail="Контакт не найден")
        recipient = contact
    else:
        result = await db.execute(
            select(ContactPoint).where(
                ContactPoint.customer_id == customer.id,
                ContactPoint.channel == channel,
            )
        )
        candidates = list(result.scalars().all())
        recipient = next(
            (c for c in candidates if c.is_primary),
            candidates[0] if candidates else None,
        )

    if not recipient:
        raise HTTPException(
            status_code=400,
            detail=f"У клиента нет контакта в канале «{channel}»",
        )

    note = await _deliver(db, channel, recipient, payload.content, current_user, conv)

    message = LeadMessage(
        lead_id=conv.lead_id,
        conversation_id=conv.id,
        channel=channel,
        direction="outbound",
        content=payload.content,
        author_id=current_user.id,
        meta={"recipient": recipient.value, "delivered": note is None},
        is_read=True,
    )
    db.add(message)

    from datetime import datetime, timezone

    conv.last_message_at = datetime.now(timezone.utc)
    conv.updated_at = conv.last_message_at

    await db.commit()
    await db.refresh(message)

    return MessageSendResponse(
        ok=note is None,
        message=MessageResponse(
            id=message.id,
            channel=message.channel,
            direction=message.direction,
            content=message.content,
            is_read=message.is_read,
            author_name=current_user.full_name,
            created_at=message.created_at,
        ),
        note=note,
    )


async def _deliver(
    db: AsyncSession,
    channel: str,
    recipient: ContactPoint,
    content: str,
    current_user: User,
    conv: Conversation,
) -> Optional[str]:
    """Пытаемся отправить. Возвращает текст замечания, если не получилось."""
    if channel == "email":
        from app.services.mail import MailError, send_email

        try:
            await send_email(db, recipient.value, "Ответ из CRM", content)
            return None
        except MailError as exc:
            logger_warning(str(exc))
            return f"Письмо не отправлено: {exc}"

    if channel == "telegram":
        from app.services import gateway

        if gateway.is_configured():
            address = str(recipient.external_id or "")
            if not address:
                value = str(recipient.value or "")
                if value.lstrip("-").isdigit():
                    address = value
                elif value:
                    try:
                        address = (
                            await gateway.resolve_telegram(value.lstrip("@")) or ""
                        )
                    except gateway.GatewayError as exc:
                        logger_warning(str(exc))
                        address = ""
            if not address:
                return (
                    "Открытого чата в Telegram нет: бот не может написать первым — "
                    "попросите клиента отправить боту любое сообщение (/start), "
                    "после этого доставка заработает"
                )
            if recipient.external_id != address:
                recipient.external_id = address
            try:
                await gateway.enqueue_outbound(address, content, source="telegram")
                return None
            except gateway.GatewayError as exc:
                return f"Шлюз не принял сообщение: {exc}"

        token = await _integration_token(db, "telegram")
        if not token:
            return "Telegram не подключён — сообщение сохранено в истории"
        address = str(recipient.value or "")
        if address and not address.lstrip("-").isdigit():
            address = "@" + address.lstrip("@")
        try:
            await _send_telegram(token, address, content)
            return None
        except Exception as exc:  # noqa: BLE001
            logger_warning(str(exc))
            return f"Telegram не отправил сообщение: {exc}"

    if channel == "avito":
        from app.services import gateway

        if not recipient.external_id:
            return (
                "Не найден идентификатор диалога Авито: "
                "дождитесь входящего сообщения в этом чате, чтобы ответить"
            )

        if gateway.is_configured():
            try:
                await gateway.enqueue_outbound(str(recipient.external_id), content)
                return None
            except gateway.GatewayError as exc:
                return f"Шлюз не принял сообщение: {exc}"

        from app.services.avito import (
            AvitoError,
            account_user_id,
            load_integration,
            send_text,
        )

        try:
            item = await load_integration(db)
            user_id = account_user_id(item)
            await send_text(db, user_id, str(recipient.external_id), content)
            return None
        except AvitoError as exc:
            logger_warning(str(exc))
            return f"Ошибка отправки в Авито: {exc}"

    if channel == "vk":
        return f"Отправка в канал «{channel}» пока не настроена — сообщение сохранено"

    return None


def logger_warning(text: str) -> None:
    import logging

    logging.getLogger(__name__).warning(text)


async def _integration_token(db: AsyncSession, name: str) -> Optional[str]:
    from app.models import IntegrationSetting

    result = await db.execute(
        select(IntegrationSetting).where(IntegrationSetting.name == name)
    )
    item = result.scalars().first()
    if not item or not item.is_enabled:
        return None
    return (item.secret or {}).get("bot_token")


async def _send_telegram(token: str, chat_id: str, text: str) -> None:
    import httpx

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, json={"chat_id": chat_id, "text": text})
        response.raise_for_status()


@router.post("/{conversation_id}/close")
async def close_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Закрывает чат, сделку не трогаем.

    Пометка «сделки нет» подставляется отдельным полем deal_state,
    а переписка остаётся доступной.
    """
    conv = await _load_conversation(db, conversation_id)
    conv.status = "closed"
    conv.unread_count = 0
    await db.commit()
    return {"ok": True, "status": conv.status}


@router.post("/{conversation_id}/open")
async def reopen_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = await _load_conversation(db, conversation_id)
    conv.status = "open"
    await db.commit()
    return {"ok": True, "status": conv.status}


@router.post("/{conversation_id}/archive")
async def archive_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Скрывает чат из ленты: история остаётся, входящие не мигают.

    Годится для почтового спама — скрытый чат не поднимается обратно.
    """
    conv = await _load_conversation(db, conversation_id)
    conv.is_archived = True
    conv.unread_count = 0
    await db.commit()
    return {"ok": True, "is_archived": True}


@router.post("/{conversation_id}/unarchive")
async def unarchive_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = await _load_conversation(db, conversation_id)
    conv.is_archived = False
    await db.commit()
    return {"ok": True, "is_archived": False}


# --- Контактные точки ---


async def _duplicate_info(
    db: AsyncSession,
    channel: str,
    value: str,
    own_customer_id: UUID,
    exclude_contact_id: Optional[UUID] = None,
) -> Optional[dict]:
    """Дубль адреса: сначала ищем у того же клиента, затем у других клиентов."""
    stmt = (
        select(ContactPoint, Customer)
        .join(Customer, ContactPoint.customer_id == Customer.id)
        .where(ContactPoint.channel == channel, ContactPoint.value == value)
    )
    if exclude_contact_id:
        stmt = stmt.where(ContactPoint.id != exclude_contact_id)
    rows = (await db.execute(stmt)).all()

    matched = next(
        (r for r in rows if r[0].customer_id == own_customer_id), None
    )
    if matched:
        cp, cust = matched
        return {
            "code": "duplicate",
            "scope": "same",
            "contact_id": str(cp.id),
            "customer_id": str(cust.id),
            "customer_name": cust.full_name,
            "is_primary": cp.is_primary,
            "value": value,
        }

    if rows:
        cp, cust = rows[0]
        return {
            "code": "duplicate",
            "scope": "other",
            "contact_id": str(cp.id),
            "customer_id": str(cust.id),
            "customer_name": cust.full_name,
            "is_primary": cp.is_primary,
            "value": value,
        }
    return None


@router.get(
    "/contacts/{customer_id}", response_model=List[ContactPointResponse]
)
async def list_contacts(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _load_customer(db, customer_id)
    result = await db.execute(
        select(ContactPoint).where(ContactPoint.customer_id == customer_id)
    )
    return [ContactPointResponse.model_validate(c) for c in result.scalars().all()]


@router.post(
    "/contacts/{customer_id}",
    response_model=ContactPointResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_contact(
    customer_id: UUID,
    payload: ContactPointCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _load_customer(db, customer_id)

    channel = payload.channel.strip().lower()
    value = normalize_value(channel, payload.value)

    dup = await _duplicate_info(db, channel, value, customer_id)
    if dup and (dup["scope"] == "same" or not payload.force):
        raise HTTPException(status_code=409, detail=dup)

    contact = ContactPoint(
        customer_id=customer_id,
        channel=channel,
        value=value,
        label=payload.label,
        is_primary=payload.is_primary,
        is_verified=False,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.patch(
    "/contacts/{contact_id}", response_model=ContactPointResponse
)
async def update_contact(
    contact_id: UUID,
    payload: ContactPointUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contact = await db.get(ContactPoint, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Контакт не найден")

    if payload.value is not None and payload.value.strip():
        new_value = normalize_value(contact.channel, payload.value)
        if new_value != contact.value:
            dup = await _duplicate_info(
                db,
                contact.channel,
                new_value,
                contact.customer_id,
                exclude_contact_id=contact.id,
            )
            if dup and (dup["scope"] == "same" or not payload.force):
                raise HTTPException(status_code=409, detail=dup)
            contact.value = new_value

    if payload.label is not None:
        contact.label = payload.label
    if payload.is_primary is not None:
        if payload.is_primary:
            # Основной может быть только один в канале
            others = await db.execute(
                select(ContactPoint).where(
                    ContactPoint.customer_id == contact.customer_id,
                    ContactPoint.channel == contact.channel,
                    ContactPoint.id != contact.id,
                )
            )
            for other in others.scalars().all():
                other.is_primary = False
        contact.is_primary = payload.is_primary

    await db.commit()
    await db.refresh(contact)
    return contact


@router.delete("/contacts/{contact_id}")
async def delete_contact(
    contact_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contact = await db.get(ContactPoint, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Контакт не найден")

    await db.delete(contact)
    await db.commit()
    return {"ok": True}
"""Схемы раздела «Сообщения»."""

from datetime import datetime
from typing import List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContactPointResponse(BaseModel):
    id: UUID
    channel: str
    value: str
    label: Optional[str] = None
    is_primary: bool = False
    is_verified: bool = False

    model_config = ConfigDict(from_attributes=True)


class ContactPointCreate(BaseModel):
    channel: str
    value: str
    label: Optional[str] = None
    is_primary: bool = False
    force: bool = False  # игнорировать дубль у другого клиента

    @field_validator("value")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Укажите адрес или номер")
        return v.strip()


class ContactPointUpdate(BaseModel):
    value: Optional[str] = None
    label: Optional[str] = None
    is_primary: Optional[bool] = None
    force: bool = False  # игнорировать дубль у другого клиента


class ConversationListResponse(BaseModel):
    id: UUID
    status: str
    is_archived: bool = False
    last_message_at: Optional[datetime] = None
    unread_count: int = 0
    customer_id: UUID
    customer_name: str
    lead_id: Optional[UUID] = None
    # Метка сделки: в работе / заключена / отказ / нет сделки
    deal_state: str = Field("none", description="active / won / lost / none")
    preview: Optional[str] = None
    channel: Optional[str] = None
    # Последнее сообщение пришло от клиента — мы ещё не ответили
    awaiting_reply: bool = False
    contacts: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AttachmentItem(BaseModel):
    """Вложение сообщения: файл в uploads/ или внешняя ссылка."""

    url: str
    name: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None


class MessageResponse(BaseModel):
    id: UUID
    channel: str
    direction: str
    content: str
    is_read: bool = False
    # Для исходящих: False — канал не принял сообщение (причина в note)
    delivered: Optional[bool] = None
    author_name: Optional[str] = None
    subject: Optional[str] = None
    attachments: List[AttachmentItem] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailResponse(BaseModel):
    id: UUID
    status: str
    is_archived: bool = False
    last_message_at: Optional[datetime] = None
    unread_count: int = 0
    customer_id: UUID
    customer_name: str
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    lead_id: Optional[UUID] = None
    deal_state: str = Field("none", description="active / won / lost / none")
    contacts: List[ContactPointResponse] = Field(default_factory=list)
    messages: List[MessageResponse] = Field(default_factory=list)
    channels: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AttachmentIn(BaseModel):
    """Вложение в запросе на отправку (поля берутся из ответа загрузки)."""

    url: str
    name: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None


class MessageCreate(BaseModel):
    """Отправка исходящего сообщения в выбранный канал."""

    channel: str
    content: str
    contact_id: Optional[UUID] = Field(
        None, description="Куда отправлять; пусто = основной контакт канала"
    )
    attachments: List[Union[AttachmentIn, str]] = Field(
        default_factory=list,
        description=(
            "Вложения из /uploads/messages (после загрузки через /attachments): "
            "объекты {url, name, content_type, size} или просто строки-url"
        ),
    )

    @field_validator("content")
    @classmethod
    def _content_not_empty(cls, v: str) -> str:
        return v or ""

    @field_validator("attachments")
    @classmethod
    def _attachments_normalize(cls, v: list) -> list:
        # Строки (старый формат) превращаем в AttachmentIn; url проверяет send_message
        return [AttachmentIn(url=a) if isinstance(a, str) else a for a in v]


class MessageSendResponse(BaseModel):
    ok: bool = True
    message: MessageResponse
    # Если канал не подключён, отдаём причину
    note: Optional[str] = None

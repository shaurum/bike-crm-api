"""Схемы раздела «Сообщения»."""

from datetime import datetime
from typing import List, Optional
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
    # Пометка «сделки нет / не в аренде»
    deal_state: str = Field("none", description="active / deal_closed / none")
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
    deal_state: str = "none"
    contacts: List[ContactPointResponse] = Field(default_factory=list)
    messages: List[MessageResponse] = Field(default_factory=list)
    channels: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class MessageCreate(BaseModel):
    """Отправка исходящего сообщения в выбранный канал."""

    channel: str
    content: str
    contact_id: Optional[UUID] = Field(
        None, description="Куда отправлять; пусто = основной контакт канала"
    )
    attachments: List[str] = Field(
        default_factory=list,
        description="URL вложений из /uploads (после загрузки через /attachments)",
    )

    @field_validator("content")
    @classmethod
    def _content_not_empty(cls, v: str) -> str:
        return v or ""

    @field_validator("attachments")
    @classmethod
    def _attachments_local(cls, v: list) -> list:
        for url in v:
            if not isinstance(url, str) or not url.startswith("/uploads/"):
                raise ValueError("Вложение должно быть файлом из uploads")
        return v


class MessageSendResponse(BaseModel):
    ok: bool = True
    message: MessageResponse
    # Если канал не подключён, отдаём причину
    note: Optional[str] = None

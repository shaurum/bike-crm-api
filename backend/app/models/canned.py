"""Предзаписанные сообщения: готовые ответы клиентам в чатах."""

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class CannedReply(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "canned_reply"

    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Название для списка"
    )
    text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Текст сообщения"
    )
    shortcut: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True, comment="Быстрая команда, напр. /привет"
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Автор",
    )

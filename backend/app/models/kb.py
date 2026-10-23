"""Библиотека знаний: статьи команды (инструкции, правила, ответы клиентам)."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class KBArticle(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "kb_article"

    title: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="Заголовок"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="Текст статьи"
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True, comment="Раздел/категория"
    )
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="Закреплена сверху"
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Автор",
    )

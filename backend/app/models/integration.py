"""Настройки интеграций (почта, Telegram, Авито и другие)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IntegrationSetting(Base):
    """Подключение внешнего сервиса.

    В `config` лежат обычные настройки, в `secret` — пароли и токены.
    Секреты не отдаются наружу, клиент видит только признак «задано / не задано».
    """

    __tablename__ = "integration_setting"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="Ключ: email, telegram, avito, vk, widget"
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False, comment="Название в интерфейсе")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    secret: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_integration_setting_name", "name", unique=True),
    )

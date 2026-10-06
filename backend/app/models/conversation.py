"""Диалоги и способы связи клиента.

ContactPoint - один способ связи (почта, телеграм, вотсап).
Conversation - чат с клиентом, один на клиента, переживает сделки.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ContactPoint(Base):
    """Способ связи клиента. Их может быть несколько."""

    __tablename__ = "contact_point"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customer.id", ondelete="CASCADE"),
        nullable=False,
        comment="Клиент",
    )
    channel: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="email, telegram, whatsapp, phone, vk"
    )
    value: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="zzz@ya.ru, +79001234567, @login"
    )
    label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    customer = relationship("Customer", lazy="noload")

    __table_args__ = (
        UniqueConstraint("customer_id", "channel", "value", name="uq_contact_point_value"),
    )


class Conversation(Base):
    """Чат с клиентом. Один на клиента."""

    __tablename__ = "conversation"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customer.id", ondelete="CASCADE"),
        nullable=False,
        comment="Клиент",
    )
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead.id", ondelete="SET NULL"),
        nullable=True,
        comment="Текущая активная сделка, если она есть",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", comment="open / closed"
    )
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    customer = relationship("Customer", lazy="selectin")
    lead = relationship("Lead", lazy="noload")

    __table_args__ = (
        UniqueConstraint("customer_id", name="uq_conversation_customer"),
    )

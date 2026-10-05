import enum
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Text, Integer, ForeignKey, Enum as SQLEnum, Index, JSON, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.models.base import Base, UUIDMixin, TimestampMixin


class LeadSourceType(str, enum.Enum):
    AVITO = "avito"
    VK = "vk"
    TELEGRAM = "telegram"
    EMAIL = "email"
    WIDGET = "widget"
    MANUAL = "manual"


class LeadStatus(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    BOOKING = "booking"
    WON = "won"
    LOST = "lost"


class TaskType(str, enum.Enum):
    CALL = "call"
    MEETING = "meeting"
    CONTRACT = "contract"
    MAINTENANCE = "maintenance"
    HANDOVER = "handover"
    RETURN = "return"
    CUSTOM = "custom"


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class LeadSource(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "lead_source"

    type: Mapped[LeadSourceType] = mapped_column(
        SQLEnum(LeadSourceType, native_enum=False, values_callable=lambda x: [m.value for m in x]),
        nullable=False,
        comment="Тип источника",
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="Название источника")
    config: Mapped[dict] = mapped_column(
        JSONB,
        default={},
        nullable=False,
        comment="Конфигурация источника (токены, ID групп и т.д.)",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="Активен ли источник")

    leads: Mapped[List["Lead"]] = relationship(back_populates="source", lazy="selectin")

    __table_args__ = (
        Index("ix_lead_source_type_active", "type", "is_active"),
    )


class PipelineStage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pipeline_stage"

    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="Название этапа")
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="Порядок сортировки")
    color: Mapped[str] = mapped_column(String(7), default="#3B82F6", nullable=False, comment="HEX цвет для UI")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="Этап по умолчанию для новых лидов")
    auto_actions: Mapped[dict] = mapped_column(
        JSONB,
        default={},
        nullable=False,
        comment="Автоматические действия при входе на этап (напр. создать задачу, отправить сообщение)",
    )

    leads: Mapped[List["Lead"]] = relationship(back_populates="stage", lazy="selectin")

    __table_args__ = (
        Index("ix_pipeline_stage_order", "order"),
    )


class Lead(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "lead"

    source_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead_source.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Источник лида",
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, comment="ID во внешней системе")
    raw_payload: Mapped[dict] = mapped_column(JSONB, default={}, nullable=False, comment="Сырые данные вебхука")

    client_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Имя клиента")
    client_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="Телефон клиента")
    client_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Email клиента")

    status: Mapped[LeadStatus] = mapped_column(
        SQLEnum(LeadStatus, native_enum=False, values_callable=lambda x: [m.value for m in x]),
        default=LeadStatus.NEW,
        nullable=False,
        comment="Статус лида",
    )
    stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("pipeline_stage.id", ondelete="SET NULL"),
        nullable=True,
        comment="Текущий этап воронки",
    )
    assigned_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Ответственный менеджер",
    )

    utm: Mapped[dict] = mapped_column(JSONB, default={}, nullable=False, comment="UTM-метки")
    initial_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Первое сообщение клиента")

    source: Mapped["LeadSource"] = relationship(back_populates="leads", lazy="selectin")
    stage: Mapped[Optional["PipelineStage"]] = relationship(back_populates="leads", lazy="selectin")
    messages: Mapped[List["LeadMessage"]] = relationship(back_populates="lead", lazy="selectin", cascade="all, delete-orphan")
    tasks: Mapped[List["Task"]] = relationship(back_populates="lead", lazy="selectin")
    assigned_to: Mapped[Optional["User"]] = relationship(back_populates="assigned_leads", lazy="selectin")

    __table_args__ = (
        Index("ix_lead_source_external_id", "source_id", "external_id", unique=True),
        Index("ix_lead_status_stage", "status", "stage_id"),
        Index("ix_lead_assigned_to", "assigned_to_id"),
        Index("ix_lead_phone", "client_phone"),
        Index("ix_lead_created_at", "created_at"),
    )


class LeadMessage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "lead_message"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead.id", ondelete="CASCADE"),
        nullable=False,
        comment="Лид",
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False, comment="Канал: avito, vk, telegram, email, internal")
    direction: Mapped[str] = mapped_column(String(20), nullable=False, comment="inbound / outbound")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="Текст сообщения")
    external_msg_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="ID сообщения во внешней системе")
    meta: Mapped[dict] = mapped_column(JSONB, default={}, nullable=False, comment="Дополнительные метаданные")

    lead: Mapped["Lead"] = relationship(back_populates="messages", lazy="selectin")

    __table_args__ = (
        Index("ix_lead_message_lead_created", "lead_id", "created_at"),
        Index("ix_lead_message_external", "external_msg_id"),
    )


class Task(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "task"

    type: Mapped[TaskType] = mapped_column(
        SQLEnum(TaskType, native_enum=False, values_callable=lambda x: [m.value for m in x]),
        nullable=False,
        comment="Тип задачи",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="Название")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Описание")
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, comment="Дедлайн")
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, native_enum=False, values_callable=lambda x: [m.value for m in x]),
        default=TaskStatus.TODO,
        nullable=False,
        comment="Статус",
    )

    related_lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead.id", ondelete="SET NULL"),
        nullable=True,
        comment="Связанный лид",
    )
    related_booking_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("booking.id", ondelete="SET NULL"),
        nullable=True,
        comment="Связанная бронь",
    )
    related_bike_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("bike.id", ondelete="SET NULL"),
        nullable=True,
        comment="Связанный байк",
    )
    assignee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Исполнитель",
    )

    lead: Mapped[Optional["Lead"]] = relationship(back_populates="tasks", lazy="selectin")
    booking: Mapped[Optional["Booking"]] = relationship(back_populates="tasks", lazy="selectin")
    bike: Mapped[Optional["Bike"]] = relationship(back_populates="tasks", lazy="selectin")
    assignee: Mapped[Optional["User"]] = relationship(back_populates="assigned_tasks", lazy="selectin")

    __table_args__ = (
        Index("ix_task_status_due", "status", "due_at"),
        Index("ix_task_assignee", "assignee_id"),
        Index("ix_task_related_lead", "related_lead_id"),
        Index("ix_task_related_booking", "related_booking_id"),
        Index("ix_task_related_bike", "related_bike_id"),
    )


class BookingWidget(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "booking_widget"

    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, comment="Домен для виджета")
    config: Mapped[dict] = mapped_column(JSONB, default={}, nullable=False, comment="Настройки виджета (тема, цвета, UTM по умолчанию)")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="Активен ли виджет")

    __table_args__ = (
        Index("ix_booking_widget_domain_active", "domain", "is_active"),
    )


class ContractTemplate(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "contract_template"

    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="Название шаблона")
    html_template: Mapped[str] = mapped_column(Text, nullable=False, comment="Jinja2 HTML шаблон")
    variables: Mapped[dict] = mapped_column(JSONB, default={}, nullable=False, comment="Описание переменных для UI")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="Шаблон по умолчанию")
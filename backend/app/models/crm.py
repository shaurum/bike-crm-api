import enum
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Text, Integer, ForeignKey, Enum as SQLEnum, Index, JSON, Boolean, DateTime, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.models.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin


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


class TaskPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class LeadSource(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "lead_source"

    type: Mapped[LeadSourceType] = mapped_column(
        SQLEnum(LeadSourceType, name="lead_source_type_enum", values_callable=lambda x: [m.value for m in x]),
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


class Lead(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
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
        SQLEnum(LeadStatus, name="lead_status_enum", values_callable=lambda x: [m.value for m in x]),
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

    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customer.id", ondelete="SET NULL"),
        nullable=True,
        comment="Привязанный клиент",
    )
    bike_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("bike.id", ondelete="SET NULL"),
        nullable=True,
        comment="Выбранный байк",
    )
    amount: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2), nullable=True, comment="Сумма по сделке"
    )
    deal_due_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Срок появления сделки"
    )
    rental_start_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Начало аренды"
    )
    rental_end_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Окончание аренды"
    )

    source: Mapped["LeadSource"] = relationship(back_populates="leads", lazy="selectin")
    stage: Mapped[Optional["PipelineStage"]] = relationship(back_populates="leads", lazy="selectin")
    # История переписки живёт в чате и должна переживать удаление сделки.
    # Раньше здесь стоял cascade="all, delete-orphan": SQLAlchemy удалял
    # сообщения в Python раньше, чем успевал сработать ON DELETE SET NULL.
    messages: Mapped[List["LeadMessage"]] = relationship(
        back_populates="lead",
        lazy="selectin",
        passive_deletes=True,
    )
    tasks: Mapped[List["Task"]] = relationship(back_populates="lead", lazy="selectin")
    assigned_to: Mapped[Optional["User"]] = relationship(back_populates="assigned_leads", lazy="selectin")
    customer: Mapped[Optional["Customer"]] = relationship(lazy="selectin")
    bike: Mapped[Optional["Bike"]] = relationship(lazy="selectin")
    comments: Mapped[List["LeadComment"]] = relationship(
        back_populates="lead",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="LeadComment.created_at",
    )

    __table_args__ = (
        Index("ix_lead_source_external_id", "source_id", "external_id", unique=True),
        Index("ix_lead_status_stage", "status", "stage_id"),
        Index("ix_lead_assigned_to", "assigned_to_id"),
        Index("ix_lead_phone", "client_phone"),
        Index("ix_lead_created_at", "created_at"),
    )


class LeadMessage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "lead_message"

    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead.id", ondelete="SET NULL"),
        nullable=True,
        comment="Deal if present",
    )
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=True,
        comment="Conversation with the client",
    )
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Who sent the outbound message",
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="Read by manager"
    )
    channel: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Channel: avito, vk, telegram, email, internal"
    )
    direction: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="inbound / outbound"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="Message text")
    attachments: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'"),
        default=list,
        comment="Вложения: [{url, name, content_type}]",
    )
    external_msg_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="Message id in external system"
    )
    meta: Mapped[dict] = mapped_column(JSONB, default={}, nullable=False, comment="Extra data")

    lead: Mapped[Optional["Lead"]] = relationship(back_populates="messages", lazy="noload")

    __table_args__ = (
        Index("ix_lead_message_lead_created", "lead_id", "created_at"),
        Index("ix_lead_message_external", "external_msg_id"),
        Index(
            "uq_lead_message_external_unique",
            "channel",
            "external_msg_id",
            unique=True,
            postgresql_where=text("external_msg_id IS NOT NULL"),
        ),
    )


class Task(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "task"

    type: Mapped[TaskType] = mapped_column(
        SQLEnum(TaskType, name="task_type_enum", values_callable=lambda x: [m.value for m in x]),
        nullable=False,
        comment="Тип задачи",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="Название")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Описание")
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, comment="Дедлайн")
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, name="task_status_enum", values_callable=lambda x: [m.value for m in x]),
        default=TaskStatus.TODO,
        nullable=False,
        comment="Статус",
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SQLEnum(TaskPriority, native_enum=False, length=10, values_callable=lambda x: [m.value for m in x]),
        default=TaskPriority.NORMAL,
        server_default="normal",
        nullable=False,
        comment="Приоритет",
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
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Кто создал",
    )

    lead: Mapped[Optional["Lead"]] = relationship(back_populates="tasks", lazy="selectin")
    booking: Mapped[Optional["Booking"]] = relationship(back_populates="tasks", lazy="selectin")
    bike: Mapped[Optional["Bike"]] = relationship(back_populates="tasks", lazy="selectin")
    assignee: Mapped[Optional["User"]] = relationship(
        back_populates="assigned_tasks", lazy="selectin", foreign_keys=[assignee_id]
    )
    created_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by_id], lazy="selectin"
    )

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

class DocumentKind(str, enum.Enum):
    CONTRACT_RENTAL = "contract_rental"
    ACT_HANDOVER = "act_handover"
    ACT_RETURN = "act_return"
    MEMO = "memo"
    SCAN = "scan"
    OTHER = "other"


class DocumentStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    SIGNED = "signed"
    CANCELLED = "cancelled"


class Document(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "document"

    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customer.id", ondelete="CASCADE"),
        nullable=True,
        comment="Клиент",
    )
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead.id", ondelete="SET NULL"),
        nullable=True,
        comment="Сделка",
    )
    bike_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("bike.id", ondelete="SET NULL"),
        nullable=True,
        comment="Байк",
    )
    kind: Mapped[DocumentKind] = mapped_column(
        SQLEnum(DocumentKind, native_enum=False, length=40, values_callable=lambda x: [m.value for m in x]),
        default=DocumentKind.CONTRACT_RENTAL,
        nullable=False,
        comment="Тип документа",
    )
    status: Mapped[DocumentStatus] = mapped_column(
        SQLEnum(DocumentStatus, native_enum=False, length=20, values_callable=lambda x: [m.value for m in x]),
        default=DocumentStatus.DRAFT,
        nullable=False,
        comment="Статус",
    )
    number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    issued_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Дата выдачи"
    )
    file_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    original_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    signed_file_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="Подписанный скан"
    )
    signed_original_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    signed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Когда приложен скан"
    )
    signed_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(
        JSON, default={}, nullable=False, comment="Данные на момент формирования"
    )

    customer: Mapped[Optional["Customer"]] = relationship(lazy="selectin")
    lead: Mapped[Optional["Lead"]] = relationship(lazy="selectin")
    bike: Mapped[Optional["Bike"]] = relationship(lazy="selectin")

    __table_args__ = (
        Index("ix_document_customer", "customer_id"),
        Index("ix_document_lead", "lead_id"),
        Index("ix_document_status", "status"),
        Index("ix_document_kind", "kind"),
    )


class CompanyProfile(UUIDMixin, TimestampMixin, Base):
    """Реквизиты арендодателя для подстановки в договор."""

    __tablename__ = "company_profile"

    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Название или ФИО ИП")
    ogrnip: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="ОГРНИП или ОГРН")
    inn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="ИНН")
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    return_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="Адрес возврата")
    age_restriction: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    deposit_return: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    photo_consent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class LeadComment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "lead_comment"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead.id", ondelete="CASCADE"),
        nullable=False,
        comment="Лид",
    )
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Автор комментария",
    )
    text: Mapped[str] = mapped_column(Text, nullable=False, comment="Текст комментария")

    lead: Mapped["Lead"] = relationship(back_populates="comments")
    author: Mapped[Optional["User"]] = relationship(lazy="selectin")

    __table_args__ = (
        Index("ix_lead_comment_lead_created", "lead_id", "created_at"),
    )

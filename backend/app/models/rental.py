import enum
import uuid
from datetime import date, datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Text, Integer, Float, ForeignKey, Enum as SQLEnum, Index, Boolean, DateTime, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.models.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin


class BikeStatus(str, enum.Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    RENTED = "rented"
    MAINTENANCE = "maintenance"
    CHARGING = "charging"
    RELOCATION = "relocation"


class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    MECHANIC = "mechanic"


class Branch(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "branch"

    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="Название филиала")
    address: Mapped[str] = mapped_column(String(255), nullable=False, comment="Адрес")
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="Телефон")
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Email")
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Moscow", nullable=False, comment="Часовой пояс")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    bikes: Mapped[List["Bike"]] = relationship(back_populates="branch", lazy="selectin")
    bookings: Mapped[List["Booking"]] = relationship(back_populates="branch", lazy="selectin")


class Bike(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "bike"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("branch.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Филиал",
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False, comment="Модель")
    frame_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True, comment="Номер рамы/VIN")
    color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="Цвет")
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="Год выпуска")
    battery_capacity: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Ёмкость батареи (Wh)")
    max_speed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="Макс. скорость (км/ч)")
    range_km: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="Запас хода (км)")
    purchase_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Цена закупки")
    purchase_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, comment="Дата закупки")
    status: Mapped[BikeStatus] = mapped_column(
        SQLEnum(BikeStatus, native_enum=False, values_callable=lambda x: [m.value for m in x]),
        default=BikeStatus.AVAILABLE,
        nullable=False,
        comment="Статус байка",
    )
    current_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Текущее местоположение")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Примечания")
    specs: Mapped[dict] = mapped_column(JSONB, default={}, nullable=False, comment="Дополнительные характеристики (JSON)")
    photos: Mapped[List[str]] = mapped_column(JSONB, default=[], nullable=False, comment="URL фото")

    branch: Mapped["Branch"] = relationship(back_populates="bikes", lazy="selectin")
    prices: Mapped[List["BikePrice"]] = relationship(
        back_populates="bike",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="BikePrice.duration_min",
    )
    bookings: Mapped[List["Booking"]] = relationship(back_populates="bike", lazy="selectin")
    tasks: Mapped[List["Task"]] = relationship(back_populates="bike", lazy="selectin")

    __table_args__ = (
        Index("ix_bike_branch_status", "branch_id", "status"),
        Index("ix_bike_frame_number", "frame_number"),
        Index("ix_bike_status", "status"),
    )


class BikePrice(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "bike_price"

    bike_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("bike.id", ondelete="CASCADE"),
        nullable=False,
    )
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False, comment="Минимальная длительность (минуты)")
    duration_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="Макс. длительность (NULL = бесконечно)")
    price: Mapped[float] = mapped_column(Float, nullable=False, comment="Цена за период")
    deposit: Mapped[float] = mapped_column(Float, default=0, nullable=False, comment="Залог")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    bike: Mapped["Bike"] = relationship(back_populates="prices", lazy="selectin")

    __table_args__ = (
        Index("ix_bike_price_bike_active", "bike_id", "is_active"),
    )


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, comment="Email")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False, comment="Хеш пароля")
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="ФИО")
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="Телефон")
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, native_enum=False, values_callable=lambda x: [m.value for m in x]),
        default=UserRole.MANAGER,
        nullable=False,
        comment="Роль",
    )
    branch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("branch.id", ondelete="SET NULL"),
        nullable=True,
        comment="Филиал (для менеджеров/механиков)",
    )
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="Telegram chat_id для уведомлений")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    assigned_leads: Mapped[List["Lead"]] = relationship(back_populates="assigned_to", lazy="selectin")
    assigned_tasks: Mapped[List["Task"]] = relationship(back_populates="assignee", lazy="selectin")

    __table_args__ = (
        Index("ix_user_email", "email"),
        Index("ix_user_branch_role", "branch_id", "role"),
    )


class CustomerDocumentType(str, enum.Enum):
    """Документ, удостоверяющий личность. Не ограничивается РФ."""

    PASSPORT_RF = "passport_rf"
    FOREIGN_PASSPORT = "foreign_passport"
    RESIDENCE_PERMIT = "residence_permit"
    ID_CARD = "id_card"
    DRIVER_LICENSE = "driver_license"
    OTHER = "other"


class Customer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "customer"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="ФИО")
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="Телефон")
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Email")
    passport_series: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment="Серия паспорта")
    passport_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="Номер паспорта")
    passport_issued_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Кем выдан")
    passport_issued_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, comment="Когда выдан")
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Адрес регистрации")
    driver_license: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="Водительское удостоверение")

    document_type: Mapped[CustomerDocumentType] = mapped_column(
        SQLEnum(CustomerDocumentType, native_enum=False, values_callable=lambda x: [m.value for m in x]),
        default=CustomerDocumentType.PASSPORT_RF,
        nullable=False,
        comment="Тип документа, удостоверяющего личность",
    )
    country: Mapped[str] = mapped_column(
        String(100), default="Россия", nullable=False, comment="Гражданство или страна документа"
    )
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="Дата рождения")
    birth_place: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Место рождения")
    passport_code: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="Код подразделения паспорта"
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Примечания")
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="В стоп-листе")

    bookings: Mapped[List["Booking"]] = relationship(back_populates="customer", lazy="selectin")
    documents: Mapped[List["CustomerDocument"]] = relationship(
        back_populates="customer",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="CustomerDocument.created_at",
    )

    __table_args__ = (
        Index("ix_customer_phone", "phone"),
        Index("ix_customer_email", "email"),
        Index("ix_customer_passport", "passport_series", "passport_number"),
        Index("ix_customer_full_name", "full_name"),
    )


class CustomerDocument(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "customer_document"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customer.id", ondelete="CASCADE"),
        nullable=False,
        comment="Клиент",
    )
    kind: Mapped[CustomerDocumentType] = mapped_column(
        SQLEnum(CustomerDocumentType, native_enum=False, values_callable=lambda x: [m.value for m in x]),
        default=CustomerDocumentType.PASSPORT_RF,
        nullable=False,
        comment="Что за документ",
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False, comment="Путь к файлу")
    original_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Имя файла при загрузке")
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="Размер в байтах")

    customer: Mapped["Customer"] = relationship(back_populates="documents")

    __table_args__ = (
        Index("ix_customer_document_customer", "customer_id"),
    )


class Booking(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "booking"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("branch.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Филиал выдачи/приёма",
    )
    bike_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("bike.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Байк",
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customer.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Клиент",
    )
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead.id", ondelete="SET NULL"),
        nullable=True,
        comment="Исходный лид",
    )
    manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Менеджер, оформивший бронь",
    )

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="Начало аренды")
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="Окончание аренды")
    actual_start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, comment="Фактическое начало")
    actual_end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, comment="Фактический конец")

    status: Mapped[BookingStatus] = mapped_column(
        SQLEnum(BookingStatus, native_enum=False, values_callable=lambda x: [m.value for m in x]),
        default=BookingStatus.PENDING,
        nullable=False,
        comment="Статус брони",
    )

    price_per_period: Mapped[float] = mapped_column(Float, nullable=False, comment="Цена за период")
    deposit_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False, comment="Залог")
    total_price: Mapped[float] = mapped_column(Float, nullable=False, comment="Итоговая сумма")
    paid_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False, comment="Оплачено")
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="Способ оплаты")

    handover_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Примечания при выдаче")
    return_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Примечания при приёме")
    damage_report: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Акт повреждений")

    branch: Mapped["Branch"] = relationship(back_populates="bookings", lazy="selectin")
    bike: Mapped["Bike"] = relationship(back_populates="bookings", lazy="selectin")
    customer: Mapped["Customer"] = relationship(back_populates="bookings", lazy="selectin")
    lead: Mapped[Optional["Lead"]] = relationship(lazy="selectin")
    manager: Mapped[Optional["User"]] = relationship(lazy="selectin")
    tasks: Mapped[List["Task"]] = relationship(back_populates="booking", lazy="selectin")

    __table_args__ = (
        Index("ix_booking_bike_dates", "bike_id", "start_at", "end_at"),
        Index("ix_booking_customer", "customer_id"),
        Index("ix_booking_status_dates", "status", "start_at", "end_at"),
        Index("ix_booking_branch_dates", "branch_id", "start_at", "end_at"),
        Index("ix_booking_lead", "lead_id"),
    )


class MaintenanceRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_record"

    bike_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("bike.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False, comment="Тип: scheduled, repair, inspection, charging")
    description: Mapped[str] = mapped_column(Text, nullable=False, comment="Описание работ")
    cost: Mapped[float] = mapped_column(Float, default=0, nullable=False, comment="Стоимость")
    performed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="Кто выполнил")
    next_maintenance_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, comment="Следующее ТО")
    mileage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="Пробег на момент ТО")

    bike: Mapped["Bike"] = relationship(lazy="selectin")

    __table_args__ = (
        Index("ix_maintenance_bike_date", "bike_id", "created_at"),
    )

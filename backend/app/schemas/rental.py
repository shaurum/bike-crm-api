from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, EmailStr, ConfigDict, Field

from app.models import BikeStatus, BookingStatus, UserRole


class BranchBase(BaseModel):
    name: str
    address: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    timezone: str = "Europe/Moscow"
    is_active: bool = True


class BranchCreate(BranchBase):
    pass


class BranchResponse(BranchBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BikePriceBase(BaseModel):
    duration_min: int
    duration_max: Optional[int] = None
    price: float
    deposit: float = 0
    is_active: bool = True


class BikePriceCreate(BikePriceBase):
    pass


class BikePriceResponse(BikePriceBase):
    id: UUID
    bike_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BikeBase(BaseModel):
    branch_id: UUID
    model: str
    frame_number: Optional[str] = None
    color: Optional[str] = None
    year: Optional[int] = None
    battery_capacity: Optional[float] = None
    max_speed: Optional[int] = None
    range_km: Optional[int] = None
    purchase_price: Optional[float] = None
    purchase_date: Optional[datetime] = None
    status: BikeStatus = BikeStatus.AVAILABLE
    current_location: Optional[str] = None
    notes: Optional[str] = None
    specs: dict = {}
    photos: List[str] = []


class BikeUpdate(BaseModel):
    model: Optional[str] = None
    frame_number: Optional[str] = None
    color: Optional[str] = None
    year: Optional[int] = None
    battery_capacity: Optional[float] = None
    max_speed: Optional[int] = None
    range_km: Optional[int] = None
    purchase_price: Optional[float] = None
    purchase_date: Optional[datetime] = None
    status: Optional[BikeStatus] = None
    current_location: Optional[str] = None
    notes: Optional[str] = None
    specs: Optional[dict] = None
    photos: Optional[List[str]] = None


class BikeResponse(BikeBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    branch: Optional[BranchResponse] = None
    prices: List[BikePriceResponse] = []
    is_rented: bool = False
    active_booking_id: Optional[UUID] = None
    active_booking_status: Optional[str] = None
    linked_lead_id: Optional[UUID] = None
    linked_stage_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


class BikePriceTier(BaseModel):
    """Прайс-тир байка: неделя / две недели / месяц."""

    week_price: Optional[float] = None
    two_week_price: Optional[float] = None
    month_price: Optional[float] = None
    deposit: float = 0


class BikeCreate(BikeBase):
    prices: Optional[BikePriceTier] = None


class BikePatch(BaseModel):
    branch_id: Optional[UUID] = None
    model: Optional[str] = None
    frame_number: Optional[str] = None
    color: Optional[str] = None
    year: Optional[int] = None
    battery_capacity: Optional[float] = None
    max_speed: Optional[int] = None
    range_km: Optional[int] = None
    purchase_price: Optional[float] = None
    purchase_date: Optional[datetime] = None
    status: Optional[BikeStatus] = None
    current_location: Optional[str] = None
    notes: Optional[str] = None
    specs: Optional[dict] = None
    photos: Optional[List[str]] = None
    prices: Optional[BikePriceTier] = None


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    role: UserRole = UserRole.MANAGER
    branch_id: Optional[UUID] = None
    telegram_chat_id: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[UserRole] = None
    branch_id: Optional[UUID] = None
    telegram_chat_id: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    id: UUID
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerBase(BaseModel):
    full_name: str
    phone: str
    email: Optional[EmailStr] = None
    passport_series: Optional[str] = None
    passport_number: Optional[str] = None
    passport_issued_by: Optional[str] = None
    passport_issued_date: Optional[datetime] = None
    address: Optional[str] = None
    driver_license: Optional[str] = None
    notes: Optional[str] = None
    is_blacklisted: bool = False


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    passport_series: Optional[str] = None
    passport_number: Optional[str] = None
    passport_issued_by: Optional[str] = None
    passport_issued_date: Optional[datetime] = None
    address: Optional[str] = None
    driver_license: Optional[str] = None
    notes: Optional[str] = None
    is_blacklisted: Optional[bool] = None


class CustomerResponse(CustomerBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookingBase(BaseModel):
    branch_id: UUID
    bike_id: UUID
    customer_id: UUID
    lead_id: Optional[UUID] = None
    start_at: datetime
    end_at: datetime
    price_per_period: float
    deposit_amount: float = 0
    total_price: float
    payment_method: Optional[str] = None


class BookingCreate(BookingBase):
    pass


class BookingUpdate(BaseModel):
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    status: Optional[BookingStatus] = None
    price_per_period: Optional[float] = None
    deposit_amount: Optional[float] = None
    total_price: Optional[float] = None
    paid_amount: Optional[float] = None
    payment_method: Optional[str] = None
    handover_notes: Optional[str] = None
    return_notes: Optional[str] = None
    damage_report: Optional[str] = None


class BookingResponse(BookingBase):
    id: UUID
    manager_id: Optional[UUID] = None
    actual_start_at: Optional[datetime] = None
    actual_end_at: Optional[datetime] = None
    status: BookingStatus
    paid_amount: float
    handover_notes: Optional[str] = None
    return_notes: Optional[str] = None
    damage_report: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    bike: Optional[BikeResponse] = None
    customer: Optional[CustomerResponse] = None
    branch: Optional[BranchResponse] = None
    manager: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)


class MaintenanceRecordBase(BaseModel):
    bike_id: UUID
    type: str
    description: str
    cost: float = 0
    performed_by: Optional[str] = None
    next_maintenance_at: Optional[datetime] = None
    mileage: Optional[int] = None


class MaintenanceRecordCreate(MaintenanceRecordBase):
    pass


class MaintenanceRecordResponse(MaintenanceRecordBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class BikeListResponse(BaseModel):
    items: List[BikeResponse]
    total: int
    page: int
    size: int
    pages: int

    model_config = ConfigDict(from_attributes=True)


class BookingListResponse(BaseModel):
    items: List[BookingResponse]
    total: int
    page: int
    size: int
    pages: int

    model_config = ConfigDict(from_attributes=True)


class CustomerListResponse(BaseModel):
    items: List[CustomerResponse]
    total: int
    page: int
    size: int
    pages: int

    model_config = ConfigDict(from_attributes=True)


class BranchListResponse(BaseModel):
    items: List[BranchResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

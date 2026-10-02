from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, EmailStr, ConfigDict


class PublicBikePrice(BaseModel):
    duration_min: int
    duration_max: Optional[int] = None
    price: float
    deposit: float


class PublicBikeResponse(BaseModel):
    id: UUID
    model: str
    color: Optional[str] = None
    year: Optional[int] = None
    battery_capacity: Optional[float] = None
    max_speed: Optional[int] = None
    range_km: Optional[int] = None
    status: str
    photos: List[str] = []
    prices: List[PublicBikePrice] = []

    model_config = ConfigDict(from_attributes=True)


class AvailabilityRequest(BaseModel):
    start_at: str
    end_at: str
    branch_id: Optional[UUID] = None


class BikeAvailabilityResponse(BaseModel):
    bike_id: UUID
    model: str
    status: str
    available: bool
    price: Optional[float] = None
    deposit: Optional[float] = None


class AvailabilityResponse(BaseModel):
    items: List[BikeAvailabilityResponse]
    start_at: str
    end_at: str


class PublicBookingCustomer(BaseModel):
    full_name: str
    phone: str
    email: Optional[EmailStr] = None


class PublicBookingCreate(BaseModel):
    bike_id: UUID
    start_at: str
    end_at: str
    customer: PublicBookingCustomer
    utm: dict = {}


class PublicBookingResponse(BaseModel):
    booking_id: UUID
    status: str


class WidgetConfigResponse(BaseModel):
    theme: dict = {}
    default_utm: dict = {}
    fields: List[str] = ["full_name", "phone", "email"]
    colors: dict = {
        "primary": "#3B82F6",
        "secondary": "#64748B",
        "success": "#10B981",
        "warning": "#F59E0B",
        "error": "#EF4444",
    }
    texts: dict = {
        "title": "Бронирование электробайка",
        "select_dates": "Выберите даты",
        "select_bike": "Выберите байк",
        "your_data": "Ваши данные",
        "submit": "Забронировать",
        "success": "Бронь создана! Менеджер свяжется с вами в течение 15 минут.",
    }
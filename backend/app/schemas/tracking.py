from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class AccountState(BaseModel):
    """Состояние аккаунта GDEGAZEL. Сумму баланса API не отдаёт, только факт блокировки."""

    state: str
    message: Optional[str] = None


class TrackerPosition(BaseModel):
    tracker_id: Optional[int] = None
    title: Optional[str] = None
    note: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed: Optional[float] = None
    azimuth: Optional[float] = None
    satellites: Optional[int] = None
    ignition: Optional[bool] = None
    moving: Optional[bool] = None
    shock_alarm: Optional[bool] = None
    engine_locked: Optional[bool] = None
    external_power: Optional[bool] = None
    external_voltage: Optional[float] = None
    tracker_battery: Optional[int] = None
    gps_time: Optional[datetime] = None
    reception_time: Optional[datetime] = None
    online: bool = False


class FleetBike(BaseModel):
    id: UUID
    model: str
    frame_number: Optional[str] = None
    status: str
    is_rented: bool = False
    tracker_id: Optional[int] = None
    position: Optional[TrackerPosition] = None


class FleetResponse(BaseModel):
    account: AccountState
    bikes: List[FleetBike] = []
    unbound_trackers: List[TrackerPosition] = []


class BikeTrackingResponse(BaseModel):
    account: AccountState
    tracker_id: Optional[int] = None
    position: Optional[TrackerPosition] = None


class TrackerOption(BaseModel):
    tracker_id: int
    title: Optional[str] = None
    note: Optional[str] = None
    bike_id: Optional[UUID] = None


class TrackersResponse(BaseModel):
    account: AccountState
    items: List[TrackerOption] = []


class TrackPoint(BaseModel):
    latitude: float
    longitude: float
    speed: Optional[float] = None
    time: datetime


class TrackResponse(BaseModel):
    points: List[TrackPoint] = []
    dropped: int = 0

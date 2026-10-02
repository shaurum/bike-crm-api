from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, EmailStr, ConfigDict

from app.models import (
    LeadSourceType, LeadStatus, TaskType, TaskStatus,
    BikeStatus, BookingStatus, UserRole,
)


class LeadSourceBase(BaseModel):
    type: LeadSourceType
    name: str
    config: dict = {}
    is_active: bool = True


class LeadSourceCreate(LeadSourceBase):
    pass


class LeadSourceResponse(LeadSourceBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PipelineStageBase(BaseModel):
    name: str
    order: int = 0
    color: str = "#3B82F6"
    is_default: bool = False
    auto_actions: dict = {}


class PipelineStageCreate(PipelineStageBase):
    pass


class PipelineStageResponse(PipelineStageBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadMessageResponse(BaseModel):
    id: UUID
    channel: str
    direction: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadBase(BaseModel):
    source_id: UUID
    external_id: str
    raw_payload: dict = {}
    client_name: Optional[str] = None
    client_phone: Optional[str] = None
    client_email: Optional[EmailStr] = None
    status: LeadStatus = LeadStatus.NEW
    stage_id: Optional[UUID] = None
    assigned_to_id: Optional[UUID] = None
    utm: dict = {}
    initial_message: Optional[str] = None


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    status: Optional[LeadStatus] = None
    stage_id: Optional[UUID] = None
    assigned_to_id: Optional[UUID] = None


class LeadResponse(LeadBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    source: Optional[LeadSourceResponse] = None
    stage: Optional[PipelineStageResponse] = None
    messages: List[LeadMessageResponse] = []

    model_config = ConfigDict(from_attributes=True)


class TaskBase(BaseModel):
    type: TaskType
    title: str
    description: Optional[str] = None
    due_at: Optional[datetime] = None
    status: TaskStatus = TaskStatus.TODO
    related_lead_id: Optional[UUID] = None
    related_booking_id: Optional[UUID] = None
    related_bike_id: Optional[UUID] = None
    assignee_id: Optional[UUID] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_at: Optional[datetime] = None
    status: Optional[TaskStatus] = None
    assignee_id: Optional[UUID] = None


class TaskResponse(TaskBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookingWidgetBase(BaseModel):
    domain: str
    config: dict = {}
    is_active: bool = True


class BookingWidgetCreate(BookingWidgetBase):
    pass


class BookingWidgetResponse(BookingWidgetBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContractTemplateBase(BaseModel):
    name: str
    html_template: str
    variables: dict = {}
    is_default: bool = False


class ContractTemplateCreate(ContractTemplateBase):
    pass


class ContractTemplateResponse(ContractTemplateBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
"""Схемы библиотеки знаний."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class KBBase(BaseModel):
    title: str
    content: str = ""
    category: Optional[str] = None
    is_pinned: bool = False

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Название статьи обязательно")
        return v

    @field_validator("category")
    @classmethod
    def _strip_category(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


class KBCreate(KBBase):
    pass


class KBUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    is_pinned: Optional[bool] = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Название статьи обязательно")
        return v

    @field_validator("category")
    @classmethod
    def _strip_category(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


class KBResponse(KBBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


class KBListResponse(BaseModel):
    items: List[KBResponse]
    total: int
    page: int
    size: int
    pages: int

    model_config = ConfigDict(from_attributes=True)


class KBCategoriesResponse(BaseModel):
    items: List[str]

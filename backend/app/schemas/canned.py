"""Схемы предзаписанных сообщений."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CannedReplyCreate(BaseModel):
    title: str
    text: str
    shortcut: Optional[str] = None

    @field_validator("title")
    @classmethod
    def _title_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Укажите название")
        return v.strip()

    @field_validator("text")
    @classmethod
    def _text_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Текст сообщения не может быть пустым")
        return v

    @field_validator("shortcut")
    @classmethod
    def _normalize_shortcut(cls, v: Optional[str]) -> Optional[str]:
        v = (v or "").strip()
        return v or None


class CannedReplyUpdate(BaseModel):
    title: Optional[str] = None
    text: Optional[str] = None
    shortcut: Optional[str] = None


class CannedReplyResponse(BaseModel):
    id: UUID
    title: str
    text: str
    shortcut: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CannedReplyListResponse(BaseModel):
    items: List[CannedReplyResponse] = Field(default_factory=list)

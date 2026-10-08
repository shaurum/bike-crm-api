"""Пригласительные ссылки: админ создаёт токен, сотрудник регистрируется по нему."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import require_admin
from app.core.database import get_db
from app.models import Invite, User, UserRole

router = APIRouter(prefix="/invites", tags=["invites"])

DEFAULT_TTL_DAYS = 14


class InviteCreate(BaseModel):
    role: UserRole = UserRole.MANAGER
    email: Optional[EmailStr] = Field(
        default=None, description="Если задан — подойдёт только этот email"
    )
    days: int = Field(default=DEFAULT_TTL_DAYS, ge=1, le=90)


class InviteResponse(BaseModel):
    id: UUID
    token: str
    role: str
    email: Optional[str]
    expires_at: datetime
    used_at: Optional[datetime]
    created_at: datetime
    status: str  # active / used / expired


class InviteValidateResponse(BaseModel):
    ok: bool
    role: Optional[str] = None
    email: Optional[str] = None
    detail: Optional[str] = None


def _invite_status(invite: Invite, now: Optional[datetime] = None) -> str:
    if invite.used_at:
        return "used"
    now = now or datetime.now(timezone.utc)
    if invite.expires_at < now:
        return "expired"
    return "active"


def _to_response(invite: Invite) -> InviteResponse:
    return InviteResponse(
        id=invite.id,
        token=invite.token,
        role=invite.role,
        email=invite.email,
        expires_at=invite.expires_at,
        used_at=invite.used_at,
        created_at=invite.created_at,
        status=_invite_status(invite),
    )


@router.post("", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def create_invite(
    payload: InviteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    invite = Invite(
        token=secrets.token_urlsafe(24),
        role=payload.role.value,
        email=payload.email.lower() if payload.email else None,
        created_by=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=payload.days),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return _to_response(invite)


@router.get("", response_model=List[InviteResponse])
async def list_invites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(
        select(Invite).order_by(Invite.created_at.desc()).limit(100)
    )
    return [_to_response(i) for i in result.scalars().all()]


@router.delete("/{invite_id}")
async def revoke_invite(
    invite_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    invite = await db.get(Invite, invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    if invite.used_at:
        raise HTTPException(
            status_code=409, detail="Приглашение уже использовано — удалить нельзя"
        )
    await db.delete(invite)
    await db.commit()
    return {"ok": True}


@router.get("/validate/{token}", response_model=InviteValidateResponse)
async def validate_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Публичная проверка ссылки-приглашения (для страницы регистрации)."""
    result = await db.execute(select(Invite).where(Invite.token == token))
    invite = result.scalar_one_or_none()
    if not invite:
        return InviteValidateResponse(ok=False, detail="Неверная ссылка-приглашение")
    status_word = _invite_status(invite)
    if status_word == "used":
        return InviteValidateResponse(ok=False, detail="Приглашение уже использовано")
    if status_word == "expired":
        return InviteValidateResponse(ok=False, detail="Приглашение истекло")
    return InviteValidateResponse(ok=True, role=invite.role, email=invite.email)

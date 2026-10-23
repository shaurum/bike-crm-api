"""Предзаписанные сообщения: готовые ответы клиентам в чатах."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models import CannedReply, User
from app.schemas.canned import (
    CannedReplyCreate,
    CannedReplyListResponse,
    CannedReplyResponse,
    CannedReplyUpdate,
)

router = APIRouter(prefix="/canned-replies", tags=["canned"])


@router.get("", response_model=CannedReplyListResponse)
async def list_canned_replies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CannedReply).order_by(CannedReply.title)
    )
    return {"items": result.scalars().all()}


@router.post("", response_model=CannedReplyResponse, status_code=201)
async def create_canned_reply(
    payload: CannedReplyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reply = CannedReply(**payload.model_dump(), created_by_id=current_user.id)
    db.add(reply)
    await db.commit()
    await db.refresh(reply)
    return reply


@router.patch("/{reply_id}", response_model=CannedReplyResponse)
async def update_canned_reply(
    reply_id: UUID,
    payload: CannedReplyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reply = await db.get(CannedReply, reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    data = payload.model_dump(exclude_unset=True)
    if "title" in data and not (data["title"] or "").strip():
        raise HTTPException(status_code=400, detail="Название не может быть пустым")
    if "text" in data and not (data["text"] or "").strip():
        raise HTTPException(status_code=400, detail="Текст не может быть пустым")
    for field, value in data.items():
        if field == "shortcut":
            value = (value or "").strip() or None
        setattr(reply, field, value)
    await db.commit()
    await db.refresh(reply)
    return reply


@router.delete("/{reply_id}")
async def delete_canned_reply(
    reply_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reply = await db.get(CannedReply, reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    await db.delete(reply)
    await db.commit()
    return {"ok": True}

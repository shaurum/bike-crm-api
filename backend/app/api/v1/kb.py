"""Библиотека знаний: CRUD статей для команды."""

import os
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.api.v1.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models import KBArticle, User
from app.schemas.kb import (
    KBCategoriesResponse,
    KBCreate,
    KBListResponse,
    KBResponse,
    KBUpdate,
)

router = APIRouter(prefix="/kb", tags=["kb"])

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@router.get("/categories", response_model=KBCategoriesResponse)
async def list_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(KBArticle.category)
        .where(KBArticle.category.isnot(None))
        .distinct()
        .order_by(KBArticle.category)
    )
    return {"items": [row[0] for row in result.all()]}


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Картинка для статьи: сохраняется в uploads/kb/, возвращается URL для markdown."""
    ext = ALLOWED_IMAGE_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(status_code=415, detail="Поддерживаются JPG, PNG, WEBP и GIF")
    payload = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(payload) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Файл больше {settings.MAX_UPLOAD_MB} МБ")
    target_dir = os.path.join(settings.UPLOAD_DIR, "kb")
    os.makedirs(target_dir, exist_ok=True)
    filename = f"kb-{uuid.uuid4().hex}{ext}"
    with open(os.path.join(target_dir, filename), "wb") as fh:
        fh.write(payload)
    return {"url": f"/uploads/kb/{filename}"}


@router.get("", response_model=KBListResponse)
async def list_articles(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None, max_length=200),
    category: Optional[str] = Query(None, max_length=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(KBArticle)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(KBArticle.title.ilike(like), KBArticle.content.ilike(like))
        )
    if category:
        query = query.where(KBArticle.category == category)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = (
        query.order_by(KBArticle.is_pinned.desc(), KBArticle.updated_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    result = await db.execute(query)
    articles = result.scalars().all()

    return {
        "items": articles,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/{article_id}", response_model=KBResponse)
async def get_article(
    article_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.get(KBArticle, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return article


@router.post("", response_model=KBResponse, status_code=201)
async def create_article(
    payload: KBCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = KBArticle(**payload.model_dump(), created_by_id=current_user.id)
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return article


@router.patch("/{article_id}", response_model=KBResponse)
async def update_article(
    article_id: UUID,
    payload: KBUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.get(KBArticle, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(article, field, value)
    await db.commit()
    await db.refresh(article)
    return article


@router.delete("/{article_id}")
async def delete_article(
    article_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.get(KBArticle, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    await db.delete(article)
    await db.commit()
    return {"ok": True}

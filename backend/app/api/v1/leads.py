from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models import Lead, LeadSource, PipelineStage, LeadStatus, User, UserRole

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("")
async def list_leads(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[LeadStatus] = None,
    stage_id: Optional[UUID] = None,
    source_id: Optional[UUID] = None,
    assigned_to_id: Optional[UUID] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Lead).options(
        selectinload(Lead.source),
        selectinload(Lead.stage),
        selectinload(Lead.assigned_to),
    )

    if status:
        query = query.where(Lead.status == status)
    if stage_id:
        query = query.where(Lead.stage_id == stage_id)
    if source_id:
        query = query.where(Lead.source_id == source_id)
    if assigned_to_id:
        query = query.where(Lead.assigned_to_id == assigned_to_id)
    if search:
        query = query.where(
            Lead.client_name.ilike(f"%{search}%") |
            Lead.client_phone.ilike(f"%{search}%") |
            Lead.client_email.ilike(f"%{search}%")
        )

    if current_user.role != UserRole.ADMIN:
        query = query.where(Lead.assigned_to_id == current_user.id)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = query.order_by(Lead.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    leads = result.scalars().all()

    return {
        "items": leads,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/{lead_id}")
async def get_lead(
    lead_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Lead)
        .options(
            selectinload(Lead.source),
            selectinload(Lead.stage),
            selectinload(Lead.assigned_to),
            selectinload(Lead.messages),
            selectinload(Lead.tasks),
        )
        .where(Lead.id == lead_id)
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")
    if current_user.role != UserRole.ADMIN and lead.assigned_to_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к этому лиду")
    return lead


@router.patch("/{lead_id}/assign")
async def assign_lead(
    lead_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только админ может назначать")
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")
    lead.assigned_to_id = user_id
    await db.commit()
    return {"message": "Лид назначен"}


@router.patch("/{lead_id}/stage")
async def change_stage(
    lead_id: UUID,
    stage_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")
    if current_user.role != UserRole.ADMIN and lead.assigned_to_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    lead.stage_id = stage_id
    await db.commit()
    return {"message": "Этап изменен"}


@router.get("/sources/list")
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LeadSource).where(LeadSource.is_active == True))
    return result.scalars().all()


@router.get("/stages/list")
async def list_stages(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PipelineStage).order_by(PipelineStage.order))
    return result.scalars().all()
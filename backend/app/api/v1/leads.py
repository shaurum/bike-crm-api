from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID, uuid4

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models import (
    Lead,
    LeadSource,
    PipelineStage,
    LeadStatus,
    LeadComment,
    Task,
    TaskType,
    TaskStatus,
    Bike,
    BikeStatus,
    User,
    UserRole,
)
from app.schemas.crm import (
    LeadResponse,
    LeadManualCreate,
    LeadListResponse,
    LeadDealUpdate,
    LeadCommentCreate,
    LeadCommentResponse,
    LeadSourceResponse,
    PipelineStageResponse,
)

router = APIRouter(prefix="/leads", tags=["leads"])


# Статус байка следует за этапом сделки, если байк привязан к лиду
STAGE_BIKE_STATUS = {
    "Новый": BikeStatus.RESERVED,
    "Связались": BikeStatus.RESERVED,
    "Договор": BikeStatus.RESERVED,
    "Оплата": BikeStatus.RESERVED,
    "Выдан": BikeStatus.RENTED,
    "Завершён": BikeStatus.AVAILABLE,
    "Отказ": BikeStatus.AVAILABLE,
}


async def sync_bike_status(db: AsyncSession, lead: Lead) -> None:
    """Переводит привязанный байк в статус, соответствующий этапу воронки."""
    if not lead.bike_id:
        return

    stage_name = None
    if lead.stage_id:
        stage = await db.get(PipelineStage, lead.stage_id)
        stage_name = stage.name if stage else None

    target = STAGE_BIKE_STATUS.get(stage_name or "")
    if target is None:
        return

    bike = await db.get(Bike, lead.bike_id)
    if not bike or bike.deleted_at is not None:
        return

    # Обслуживание важнее воронки: пока байк на ТО, этапы его не трогают
    if bike.status == BikeStatus.MAINTENANCE:
        return

    bike.status = target


@router.get("", response_model=LeadListResponse)
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
            Lead.client_name.ilike(f"%{search}%")
            | Lead.client_phone.ilike(f"%{search}%")
            | Lead.client_email.ilike(f"%{search}%")
        )

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


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadManualCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = await db.get(LeadSource, payload.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Источник лида не найден")

    default_stage = await db.scalar(
        select(PipelineStage).where(PipelineStage.is_default == True)
    )

    if payload.bike_id:
        await ensure_bike_is_free(db, payload.bike_id, None)

    # Если выбран существующий клиент — подтягиваем его контакты
    customer = None
    if payload.customer_id:
        from app.models import Customer

        customer = await db.get(Customer, payload.customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Клиент не найден")

    lead = Lead(
        source_id=source.id,
        external_id=f"manual-{uuid4().hex[:8]}",
        customer_id=customer.id if customer else None,
        client_name=(customer.full_name if customer else None) or payload.client_name,
        client_phone=(customer.phone if customer else None) or payload.client_phone,
        client_email=(customer.email if customer else None) or payload.client_email,
        bike_id=payload.bike_id,
        initial_message=payload.initial_message,
        utm=payload.utm or {},
        status=LeadStatus.NEW,
        stage_id=default_stage.id if default_stage else None,
    )
    db.add(lead)
    await db.flush()

    db.add(
        Task(
            type=TaskType.CALL,
            title="Связаться с клиентом",
            related_lead_id=lead.id,
            assignee_id=current_user.id,
            status=TaskStatus.TODO,
        )
    )
    await db.commit()

    await sync_bike_status(db, lead)

    result = await db.execute(
        select(Lead)
        .options(
            selectinload(Lead.source),
            selectinload(Lead.stage),
            selectinload(Lead.messages),
            selectinload(Lead.comments),
        )
        .where(Lead.id == lead.id)
    )
    return result.scalar_one()


@router.get("/{lead_id}", response_model=LeadResponse)
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
    return lead


# Этапы, на которых сделка закрыта — байк возвращается в парковку
TERMINAL_STAGES = {"Завершён", "Отказ"}


async def ensure_bike_is_free(db: AsyncSession, bike_id: UUID, lead_id) -> None:
    """Нельзя выдать байк, который уже занят другой незакрытой сделкой."""
    stmt = select(Lead.id).where(Lead.bike_id == bike_id)
    if lead_id is not None:
        stmt = stmt.where(Lead.id != lead_id)

    taken = (
        await db.execute(
            stmt.join(PipelineStage, Lead.stage_id == PipelineStage.id).where(
                PipelineStage.name.notin_(TERMINAL_STAGES)
            )
        )
    ).scalars().first()

    if taken:
        raise HTTPException(
            status_code=409,
            detail="Байк уже привязан к другой сделке",
        )


async def release_bike(db: AsyncSession, bike_id: UUID) -> None:
    """Возвращает байк в свободные, если он не привязан к другой сделке.

    Байк на обслуживании не трогаем — это ручной статус гаража.
    """
    bike = await db.get(Bike, bike_id)
    if not bike or bike.deleted_at is not None:
        return
    if bike.status == BikeStatus.MAINTENANCE:
        return

    other = (
        await db.execute(
            select(Lead.id)
            .join(PipelineStage, Lead.stage_id == PipelineStage.id)
            .where(Lead.bike_id == bike_id, PipelineStage.name.notin_(TERMINAL_STAGES))
            .limit(1)
        )
    ).scalars().first()
    if other:
        return

    bike.status = BikeStatus.AVAILABLE
    await db.commit()


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")

    bike_id = lead.bike_id

    # Задачи ссылаются на лид через SET NULL — удаляем явно, чтобы не осталось мусора
    await db.execute(delete(Task).where(Task.related_lead_id == lead_id))

    await db.delete(lead)
    await db.commit()

    # Освобождаем байк: без сделки он не должен висеть в аренде или резерве
    if bike_id:
        await release_bike(db, bike_id)

    return None


@router.patch("/{lead_id}/deal", response_model=LeadResponse)
async def update_deal(
    lead_id: UUID,
    payload: LeadDealUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(lead, field, value)

    bike_id = data.get("bike_id", lead.bike_id)
    if bike_id:
        await ensure_bike_is_free(db, bike_id, lead.id)

    await sync_bike_status(db, lead)
    await db.commit()

    result = await db.execute(
        select(Lead)
        .options(
            selectinload(Lead.source),
            selectinload(Lead.stage),
            selectinload(Lead.messages),
            selectinload(Lead.comments),
        )
        .where(Lead.id == lead_id)
    )
    return result.scalar_one()


@router.get("/{lead_id}/comments", response_model=List[LeadCommentResponse])
async def list_comments(
    lead_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(LeadComment)
        .options(selectinload(LeadComment.author))
        .where(LeadComment.lead_id == lead_id)
        .order_by(LeadComment.created_at)
    )
    return result.scalars().all()


@router.post(
    "/{lead_id}/comments",
    response_model=LeadCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    lead_id: UUID,
    payload: LeadCommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exists = await db.get(Lead, lead_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Лид не найден")

    comment = LeadComment(
        lead_id=lead_id,
        author_id=current_user.id,
        text=payload.text,
    )
    db.add(comment)
    await db.commit()

    result = await db.execute(
        select(LeadComment)
        .options(selectinload(LeadComment.author))
        .where(LeadComment.id == comment.id)
    )
    return result.scalar_one()


@router.patch("/{lead_id}/assign")
async def assign_lead(
    lead_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Только админ может назначать")
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
    lead.stage_id = stage_id
    if stage_id is not None:
        stage = await db.get(PipelineStage, stage_id)
        if stage and stage.name == "Отказ":
            lead.status = LeadStatus.LOST
        elif lead.status == LeadStatus.LOST:
            lead.status = LeadStatus.QUALIFIED

    await sync_bike_status(db, lead)
    await db.commit()
    return {"message": "Этап изменен"}


@router.get("/sources/list", response_model=List[LeadSourceResponse])
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LeadSource).where(LeadSource.is_active == True))
    return result.scalars().all()


@router.get("/stages/list", response_model=List[PipelineStageResponse])
async def list_stages(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PipelineStage).order_by(PipelineStage.order))
    return result.scalars().all()
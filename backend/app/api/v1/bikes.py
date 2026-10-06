import os

from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID

from app.core.config import settings
from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models import Bike, BikeStatus, BikePrice, Branch, PipelineStage, User, UserRole
from app.schemas.rental import (
    BikeResponse,
    BikeListResponse,
    BikeCreate,
    BikePatch,
    BranchListResponse,
    BranchResponse,
    BranchCreate,
)

router = APIRouter(prefix="/bikes", tags=["bikes"])


@router.get("", response_model=BikeListResponse)
async def list_bikes(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[BikeStatus] = None,
    branch_id: Optional[UUID] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(Bike)
        .options(selectinload(Bike.branch), selectinload(Bike.prices))
        .where(Bike.deleted_at.is_(None))
    )

    if status:
        query = query.where(Bike.status == status)
    if branch_id:
        query = query.where(Bike.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN and current_user.branch_id:
        query = query.where(Bike.branch_id == current_user.branch_id)
    if search:
        query = query.where(
            Bike.model.ilike(f"%{search}%") |
            Bike.frame_number.ilike(f"%{search}%")
        )

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = query.order_by(Bike.model).offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    bikes = list(result.scalars().all())

    for bike in bikes:
        await _with_rental_state(db, bike)

    return {
        "items": bikes,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/{bike_id}", response_model=BikeResponse)
async def get_bike(
    bike_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Bike)
        .options(selectinload(Bike.branch), selectinload(Bike.prices))
        .where(Bike.id == bike_id, Bike.deleted_at.is_(None))
    )
    bike = result.scalar_one_or_none()
    if not bike:
        raise HTTPException(status_code=404, detail="Байк не найден")
    return bike


@router.get("/{bike_id}/availability")
async def check_availability(
    bike_id: UUID,
    start_at: str,
    end_at: str,
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime
    start = datetime.fromisoformat(start_at.replace('Z', '+00:00'))
    end = datetime.fromisoformat(end_at.replace('Z', '+00:00'))

    result = await db.execute(
        select(Bike).where(Bike.id == bike_id, Bike.deleted_at.is_(None))
    )
    bike = result.scalar_one_or_none()
    if not bike:
        raise HTTPException(status_code=404, detail="Байк не найден")

    from app.models import Booking, BookingStatus
    result = await db.execute(
        select(Booking).where(
            Booking.bike_id == bike_id,
            Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.ACTIVE]),
            Booking.start_at < end,
            Booking.end_at > start,
        )
    )
    conflicting = result.scalars().all()

    return {
        "available": len(conflicting) == 0 and bike.status == BikeStatus.AVAILABLE,
        "conflicts": [{"id": str(b.id), "start": b.start_at, "end": b.end_at} for b in conflicting],
    }


@router.get("/branches/list", response_model=BranchListResponse)
async def list_branches(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Branch).where(Branch.is_active == True))
    return {"items": list(result.scalars().all())}


@router.post("/branches", response_model=BranchResponse, status_code=status.HTTP_201_CREATED)
async def create_branch(
    payload: BranchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch = Branch(**payload.model_dump())
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return branch


# ------------------------------------------------------------------
# CRUD байков
# ------------------------------------------------------------------

WEEK = 7 * 24 * 60
TWO_WEEKS = 14 * 24 * 60
MONTH = 30 * 24 * 60

PRICE_TIERS = [
    ("week_price", WEEK, TWO_WEEKS - 1),
    ("two_week_price", TWO_WEEKS, MONTH - 1),
    ("month_price", MONTH, None),
]


async def _apply_prices(db: AsyncSession, bike_id: UUID, tier) -> None:
    """Перезаписывает прайс-тиры байка (неделя / две недели / месяц)."""
    await db.execute(delete(BikePrice).where(BikePrice.bike_id == bike_id))
    if tier is None:
        return
    for field, duration_min, duration_max in PRICE_TIERS:
        price = getattr(tier, field, None)
        if price is None:
            continue
        db.add(
            BikePrice(
                bike_id=bike_id,
                duration_min=duration_min,
                duration_max=duration_max,
                price=price,
                deposit=tier.deposit or 0,
            )
        )


async def _active_booking(db: AsyncSession, bike_id: UUID):
    from app.models import Booking, BookingStatus

    result = await db.execute(
        select(Booking)
        .where(
            Booking.bike_id == bike_id,
            Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.ACTIVE]),
        )
        .order_by(Booking.start_at)
        .limit(1)
    )
    return result.scalars().first()


async def _with_rental_state(db: AsyncSession, bike):
    """Статус «в аренде» берём из CRM: активная бронь, а не ручной флаг."""
    from app.models import Lead
    from app.api.v1.leads import TERMINAL_STAGES

    booking = await _active_booking(db, bike.id)
    bike.is_rented = booking is not None
    bike.active_booking_id = booking.id if booking else None
    bike.active_booking_status = booking.status.value if booking else None

    # Байк считается занятым только если висит на незакрытой сделке.
    # На «Завершён» и «Отказ» сделка закрыта — байк свободен для новых лидов.
    linked = (
        await db.execute(
            select(Lead.id, Lead.stage_id, PipelineStage.name)
            .join(PipelineStage, Lead.stage_id == PipelineStage.id)
            .where(Lead.bike_id == bike.id, PipelineStage.name.notin_(TERMINAL_STAGES))
            .limit(1)
        )
    ).first()

    bike.linked_lead_id = linked[0] if linked else None
    bike.linked_stage_id = linked[1] if linked else None

    return bike


async def _load_bike(db: AsyncSession, bike_id: UUID):
    result = await db.execute(
        select(Bike)
        .options(selectinload(Bike.branch), selectinload(Bike.prices))
        .where(Bike.id == bike_id, Bike.deleted_at.is_(None))
    )
    bike = result.scalar_one_or_none()
    if not bike:
        raise HTTPException(status_code=404, detail="Байк не найден")
    return await _with_rental_state(db, bike)


async def restore_status_from_crm(db: AsyncSession, bike) -> None:
    """Возвращает статусу байка значение из этапа воронки связанной сделки."""
    from app.api.v1.leads import STAGE_BIKE_STATUS
    from app.models import Lead

    lead = (
        await db.execute(select(Lead).where(Lead.bike_id == bike.id))
    ).scalars().first()
    if not lead or not lead.stage_id:
        return

    stage = await db.get(PipelineStage, lead.stage_id)
    target = STAGE_BIKE_STATUS.get(stage.name if stage else "")
    if target is not None:
        bike.status = target


@router.post("", response_model=BikeResponse, status_code=status.HTTP_201_CREATED)
async def create_bike(
    payload: BikeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump(exclude={"prices"})
    bike = Bike(**data)
    db.add(bike)
    await db.flush()
    await _apply_prices(db, bike.id, payload.prices)
    await db.commit()
    return await _load_bike(db, bike.id)


@router.patch("/{bike_id}", response_model=BikeResponse)
async def update_bike(
    bike_id: UUID,
    payload: BikePatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bike = await db.get(Bike, bike_id)
    if not bike or bike.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Байк не найден")

    data = payload.model_dump(exclude={"prices"}, exclude_unset=True)
    for field, value in data.items():
        setattr(bike, field, value)

    # Статус ведёт воронка. Из гаража разрешено только ставить и снимать обслуживание.
    if "status" in data and data["status"] == BikeStatus.MAINTENANCE:
        bike.status = BikeStatus.MAINTENANCE
    elif "status" in data:
        await restore_status_from_crm(db, bike)

    if payload.prices is not None:
        await _apply_prices(db, bike.id, payload.prices)

    await db.commit()
    return await _load_bike(db, bike.id)


@router.delete("/{bike_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bike(
    bike_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime, timezone

    bike = await db.get(Bike, bike_id)
    if not bike or bike.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Байк не найден")

    booking = await _active_booking(db, bike_id)
    if booking:
        raise HTTPException(
            status_code=409,
            detail="Нельзя удалить байк с активной арендой",
        )

    bike.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return None


ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@router.post("/{bike_id}/photo", response_model=BikeResponse)
async def upload_photo(
    bike_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bike = await db.get(Bike, bike_id)
    if not bike or bike.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Байк не найден")

    ext = ALLOWED_IMAGE_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(
            status_code=415,
            detail="Поддерживаются только JPG, PNG, WEBP и GIF",
        )

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    filename = f"bike-{bike_id}{ext}"
    path = os.path.join(settings.UPLOAD_DIR, filename)

    payload = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Файл больше {settings.MAX_UPLOAD_MB} МБ",
        )

    with open(path, "wb") as fh:
        fh.write(payload)

    bike.photos = [f"{settings.API_V1_PREFIX.replace('/api/v1', '')}/uploads/{filename}"]
    await db.commit()
    return await _load_bike(db, bike.id)

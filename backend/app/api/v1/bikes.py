from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models import Bike, BikeStatus, BikePrice, Branch, User, UserRole
from app.schemas.rental import BikeResponse, BikeListResponse, BranchListResponse

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
    query = select(Bike).options(selectinload(Bike.branch)).where(Bike.deleted_at.is_(None))

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
    bikes = result.scalars().all()

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
    return result.scalars().all()
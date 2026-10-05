from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID
from datetime import datetime

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models import Booking, BookingStatus, Bike, BikeStatus, Customer, Branch, User, UserRole
from app.schemas.rental import BookingResponse, BookingListResponse

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("", response_model=BookingListResponse)
async def list_bookings(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[BookingStatus] = None,
    branch_id: Optional[UUID] = None,
    bike_id: Optional[UUID] = None,
    customer_id: Optional[UUID] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Booking).options(
        selectinload(Booking.bike),
        selectinload(Booking.customer),
        selectinload(Booking.branch),
        selectinload(Booking.manager),
    )

    if status:
        query = query.where(Booking.status == status)
    if branch_id:
        query = query.where(Booking.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN and current_user.branch_id:
        query = query.where(Booking.branch_id == current_user.branch_id)
    if bike_id:
        query = query.where(Booking.bike_id == bike_id)
    if customer_id:
        query = query.where(Booking.customer_id == customer_id)
    if date_from:
        query = query.where(Booking.start_at >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.where(Booking.end_at <= datetime.fromisoformat(date_to))

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = query.order_by(Booking.start_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    bookings = result.scalars().all()

    return {
        "items": bookings,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Booking)
        .options(
            selectinload(Booking.bike),
            selectinload(Booking.customer),
            selectinload(Booking.branch),
            selectinload(Booking.manager),
            selectinload(Booking.tasks),
        )
        .where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    return booking


@router.post("/{booking_id}/confirm")
async def confirm_booking(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    if booking.status != BookingStatus.PENDING:
        raise HTTPException(status_code=400, detail="Бронь не в статусе ожидания")

    booking.status = BookingStatus.CONFIRMED
    booking.manager_id = current_user.id

    bike_result = await db.execute(select(Bike).where(Bike.id == booking.bike_id))
    bike = bike_result.scalar_one_or_none()
    if bike:
        bike.status = BikeStatus.RESERVED

    await db.commit()
    return {"message": "Бронь подтверждена"}


@router.post("/{booking_id}/start")
async def start_booking(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="Бронь не подтверждена")

    booking.status = BookingStatus.ACTIVE
    booking.actual_start_at = datetime.now()
    bike_result = await db.execute(select(Bike).where(Bike.id == booking.bike_id))
    bike = bike_result.scalar_one_or_none()
    if bike:
        bike.status = BikeStatus.RENTED

    await db.commit()
    return {"message": "Аренда начата"}


@router.post("/{booking_id}/complete")
async def complete_booking(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    if booking.status != BookingStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Аренда не активна")

    booking.status = BookingStatus.COMPLETED
    booking.actual_end_at = datetime.now()
    bike_result = await db.execute(select(Bike).where(Bike.id == booking.bike_id))
    bike = bike_result.scalar_one_or_none()
    if bike:
        bike.status = BikeStatus.AVAILABLE

    await db.commit()
    return {"message": "Аренда завершена"}
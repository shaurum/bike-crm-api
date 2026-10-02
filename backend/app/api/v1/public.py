from fastapi import APIRouter, Depends, Query, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models import Bike, BikeStatus, BikePrice, Branch, BookingWidget, Booking, BookingStatus

router = APIRouter(prefix="/public", tags=["public"])


async def verify_public_api_key(x_api_key: str = Header(None)):
    from app.core.config import settings
    if x_api_key != settings.PUBLIC_API_KEY:
        raise HTTPException(status_code=401, detail="Неверный API ключ")


@router.get("/bikes")
async def list_public_bikes(
    branch_id: Optional[UUID] = None,
    available_only: bool = True,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_public_api_key),
):
    query = select(Bike).options(selectinload(Bike.prices)).where(Bike.deleted_at.is_(None))
    if available_only:
        query = query.where(Bike.status == BikeStatus.AVAILABLE)
    if branch_id:
        query = query.where(Bike.branch_id == branch_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/bikes/{bike_id}")
async def get_public_bike(
    bike_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_public_api_key),
):
    result = await db.execute(
        select(Bike)
        .options(selectinload(Bike.prices), selectinload(Bike.branch))
        .where(Bike.id == bike_id, Bike.deleted_at.is_(None))
    )
    bike = result.scalar_one_or_none()
    if not bike:
        raise HTTPException(status_code=404, detail="Байк не найден")
    return bike


@router.get("/availability")
async def check_availability(
    start_at: str,
    end_at: str,
    branch_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_public_api_key),
):
    start = datetime.fromisoformat(start_at.replace('Z', '+00:00'))
    end = datetime.fromisoformat(end_at.replace('Z', '+00:00'))

    query = select(Bike).options(selectinload(Bike.prices)).where(
        Bike.deleted_at.is_(None),
        Bike.status == BikeStatus.AVAILABLE,
    )
    if branch_id:
        query = query.where(Bike.branch_id == branch_id)

    result = await db.execute(query)
    bikes = result.scalars().all()

    availability = []
    for bike in bikes:
        conflict = await db.execute(
            select(Booking).where(
                Booking.bike_id == bike.id,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.ACTIVE]),
                Booking.start_at < end,
                Booking.end_at > start,
            )
        )
        is_available = conflict.scalar_one_or_none() is None

        prices = [p for p in bike.prices if p.is_active]
        price = None
        if prices:
            duration_minutes = int((end - start).total_seconds() / 60)
            for p in sorted(prices, key=lambda x: x.duration_max or 0):
                if p.duration_min <= duration_minutes and (p.duration_max is None or p.duration_max >= duration_minutes):
                    price = p.price
                    break

        availability.append({
            "bike_id": str(bike.id),
            "model": bike.model,
            "status": bike.status.value,
            "available": is_available,
            "price": price,
            "deposit": prices[0].deposit if prices else 0,
        })

    return {"items": availability, "start_at": start_at, "end_at": end_at}


@router.post("/bookings")
async def create_public_booking(
    booking_data: dict,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_public_api_key),
):
    from app.models import Customer, Lead, LeadSource, LeadStatus, PipelineStage

    bike_id = booking_data.get("bike_id")
    start_at = datetime.fromisoformat(booking_data.get("start_at"))
    end_at = datetime.fromisoformat(booking_data.get("end_at"))
    customer_data = booking_data.get("customer", {})

    bike_result = await db.execute(select(Bike).where(Bike.id == bike_id, Bike.deleted_at.is_(None)))
    bike = bike_result.scalar_one_or_none()
    if not bike:
        raise HTTPException(status_code=404, detail="Байк не найден")

    if bike.status != BikeStatus.AVAILABLE:
        raise HTTPException(status_code=400, detail="Байк недоступен")

    conflict = await db.execute(
        select(Booking).where(
            Booking.bike_id == bike_id,
            Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.ACTIVE]),
            Booking.start_at < end_at,
            Booking.end_at > start_at,
        )
    )
    if conflict.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Байк занят в это время")

    customer = Customer(
        full_name=customer_data.get("full_name"),
        phone=customer_data.get("phone"),
        email=customer_data.get("email"),
    )
    db.add(customer)
    await db.flush()

    widget_source = await db.execute(
        select(LeadSource).where(LeadSource.type == "widget", LeadSource.is_active == True)
    )
    source = widget_source.scalar_one_or_none()

    lead = Lead(
        source_id=source.id if source else None,
        external_id=f"widget_{customer.id}",
        client_name=customer.full_name,
        client_phone=customer.phone,
        client_email=customer.email,
        status=LeadStatus.BOOKING,
        utm=booking_data.get("utm", {}),
    )
    db.add(lead)
    await db.flush()

    price_result = await db.execute(select(BikePrice).where(BikePrice.bike_id == bike_id, BikePrice.is_active == True))
    prices = price_result.scalars().all()
    price_per_period = 0
    if prices:
        duration_minutes = int((end_at - start_at).total_seconds() / 60)
        for p in sorted(prices, key=lambda x: x.duration_max or 0):
            if p.duration_min <= duration_minutes and (p.duration_max is None or p.duration_max >= duration_minutes):
                price_per_period = p.price
                break

    booking = Booking(
        branch_id=bike.branch_id,
        bike_id=bike.id,
        customer_id=customer.id,
        lead_id=lead.id,
        start_at=start_at,
        end_at=end_at,
        status=BookingStatus.PENDING,
        price_per_period=price_per_period,
        deposit_amount=prices[0].deposit if prices else 0,
        total_price=price_per_period + (prices[0].deposit if prices else 0),
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    return {"booking_id": str(booking.id), "status": "pending"}


@router.get("/widget/config")
async def get_widget_config(
    domain: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BookingWidget).where(BookingWidget.domain == domain, BookingWidget.is_active == True)
    )
    widget = result.scalar_one_or_none()
    if not widget:
        raise HTTPException(status_code=404, detail="Виджет не найден")
    return widget.config
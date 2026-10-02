from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models import (
    Bike, BikeStatus, Booking, BookingStatus, Lead, LeadStatus,
    Task, TaskStatus, User, UserRole, PipelineStage, Branch
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = datetime.now() - timedelta(days=days)

    bikes_total = await db.scalar(select(func.count(Bike.id)).where(Bike.deleted_at.is_(None)))
    bikes_available = await db.scalar(
        select(func.count(Bike.id)).where(Bike.deleted_at.is_(None), Bike.status == BikeStatus.AVAILABLE)
    )
    bikes_rented = await db.scalar(
        select(func.count(Bike.id)).where(Bike.deleted_at.is_(None), Bike.status == BikeStatus.RENTED)
    )
    bikes_maintenance = await db.scalar(
        select(func.count(Bike.id)).where(Bike.deleted_at.is_(None), Bike.status == BikeStatus.MAINTENANCE)
    )

    bookings_total = await db.scalar(
        select(func.count(Booking.id)).where(Booking.created_at >= since)
    )
    bookings_confirmed = await db.scalar(
        select(func.count(Booking.id)).where(
            Booking.created_at >= since, Booking.status == BookingStatus.CONFIRMED
        )
    )
    bookings_completed = await db.scalar(
        select(func.count(Booking.id)).where(
            Booking.created_at >= since, Booking.status == BookingStatus.COMPLETED
        )
    )

    revenue = await db.scalar(
        select(func.coalesce(func.sum(Booking.paid_amount), 0)).where(
            Booking.created_at >= since, Booking.status == BookingStatus.COMPLETED
        )
    )

    leads_total = await db.scalar(select(func.count(Lead.id)).where(Lead.created_at >= since))
    leads_new = await db.scalar(
        select(func.count(Lead.id)).where(Lead.created_at >= since, Lead.status == LeadStatus.NEW)
    )
    leads_won = await db.scalar(
        select(func.count(Lead.id)).where(Lead.created_at >= since, Lead.status == LeadStatus.WON)
    )

    tasks_pending = await db.scalar(
        select(func.count(Task.id)).where(Task.status == TaskStatus.TODO)
    )
    tasks_overdue = await db.scalar(
        select(func.count(Task.id)).where(
            Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]),
            Task.due_at < datetime.now(),
        )
    )

    return {
        "period_days": days,
        "bikes": {
            "total": bikes_total or 0,
            "available": bikes_available or 0,
            "rented": bikes_rented or 0,
            "maintenance": bikes_maintenance or 0,
        },
        "bookings": {
            "total": bookings_total or 0,
            "confirmed": bookings_confirmed or 0,
            "completed": bookings_completed or 0,
            "conversion": round((bookings_confirmed or 0) / (leads_total or 1) * 100, 1),
        },
        "revenue": float(revenue or 0),
        "leads": {
            "total": leads_total or 0,
            "new": leads_new or 0,
            "won": leads_won or 0,
            "conversion": round((leads_won or 0) / (leads_total or 1) * 100, 1),
        },
        "tasks": {
            "pending": tasks_pending or 0,
            "overdue": tasks_overdue or 0,
        },
    }


@router.get("/funnel")
async def get_funnel(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = datetime.now() - timedelta(days=days)

    stages_result = await db.execute(
        select(PipelineStage).order_by(PipelineStage.order)
    )
    stages = stages_result.scalars().all()

    funnel = []
    for stage in stages:
        count = await db.scalar(
            select(func.count(Lead.id)).where(
                Lead.stage_id == stage.id,
                Lead.created_at >= since,
            )
        )
        funnel.append({
            "stage_id": str(stage.id),
            "stage_name": stage.name,
            "color": stage.color,
            "count": count or 0,
        })

    return {"stages": funnel}


@router.get("/bikes-utilization")
async def get_bikes_utilization(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = datetime.now() - timedelta(days=days)

    result = await db.execute(
        select(Bike)
        .options(selectinload(Bike.bookings))
        .where(Bike.deleted_at.is_(None))
    )
    bikes = result.scalars().all()

    utilization = []
    for bike in bikes:
        bookings = [b for b in bike.bookings if b.created_at >= since and b.status == BookingStatus.COMPLETED]
        total_rental_minutes = sum(
            int((b.actual_end_at - b.actual_start_at).total_seconds() / 60)
            for b in bookings if b.actual_start_at and b.actual_end_at
        )
        total_minutes = days * 24 * 60
        utilization_pct = round(total_rental_minutes / total_minutes * 100, 1) if total_minutes > 0 else 0

        utilization.append({
            "bike_id": str(bike.id),
            "model": bike.model,
            "total_bookings": len(bookings),
            "total_rental_hours": round(total_rental_minutes / 60, 1),
            "utilization_pct": utilization_pct,
        })

    return {"items": utilization}


@router.get("/leads-by-source")
async def get_leads_by_source(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = datetime.now() - timedelta(days=days)

    from app.models import LeadSource
    result = await db.execute(
        select(LeadSource, func.count(Lead.id))
        .join(Lead, Lead.source_id == LeadSource.id, isouter=True)
        .where(LeadSource.is_active == True)
        .where(Lead.created_at >= since)
        .group_by(LeadSource.id)
    )

    return [
        {"source": source.name, "type": source.type.value, "count": count}
        for source, count in result.all()
    ]
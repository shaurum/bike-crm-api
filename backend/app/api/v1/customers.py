from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models import Customer, User, UserRole

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
async def list_customers(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    is_blacklisted: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Customer)

    if search:
        query = query.where(
            Customer.full_name.ilike(f"%{search}%") |
            Customer.phone.ilike(f"%{search}%") |
            Customer.email.ilike(f"%{search}%")
        )
    if is_blacklisted is not None:
        query = query.where(Customer.is_blacklisted == is_blacklisted)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = query.order_by(Customer.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    customers = result.scalars().all()

    return {
        "items": customers,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/{customer_id}")
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Customer)
        .options(selectinload(Customer.bookings))
        .where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    return customer


@router.post("", status_code=201)
async def create_customer(
    customer_data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = Customer(**customer_data)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer
import os

from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID

from app.core.config import settings
from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models import (
    ContactPoint,
    Customer,
    CustomerDocument,
    CustomerDocumentType,
    User,
    UserRole,
)
from app.schemas.rental import (
    CustomerResponse,
    CustomerListResponse,
    CustomerCreate,
    CustomerUpdate,
    CustomerDocumentResponse,
)
from app.services.messaging import normalize_value

router = APIRouter(prefix="/customers", tags=["customers"])

ALLOWED_DOC_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


def _load(query):
    return query.options(
        selectinload(Customer.documents), selectinload(Customer.bookings)
    )


@router.get("", response_model=CustomerListResponse)
async def list_customers(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    is_blacklisted: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Customer).where(Customer.deleted_at.is_(None))

    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Customer.full_name.ilike(pattern),
                Customer.phone.ilike(pattern),
                Customer.email.ilike(pattern),
                Customer.passport_number.ilike(pattern),
                Customer.passport_series.ilike(pattern),
            )
        )
    if is_blacklisted is not None:
        query = query.where(Customer.is_blacklisted == is_blacklisted)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = (
        _load(query)
        .order_by(Customer.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    result = await db.execute(query)
    customers = result.scalars().all()

    return {
        "items": customers,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


async def _get_customer(db: AsyncSession, customer_id: UUID) -> Customer:
    result = await db.execute(
        _load(select(Customer)).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if not customer or customer.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    return customer


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_customer(db, customer_id)


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = (
        await db.execute(
            select(Customer.id).where(
                Customer.deleted_at.is_(None),
                or_(
                    Customer.phone == payload.phone,
                    Customer.email == payload.email
                    if payload.email
                    else False,
                ),
            )
        )
    ).scalars().first()
    if existing:
        raise HTTPException(
            status_code=409, detail="Клиент с таким телефоном или email уже есть"
        )

    customer = Customer(**payload.model_dump())
    db.add(customer)
    await db.flush()

    # Поля «телефон/email» — основные способы связи, дублируем их в contact_point
    for channel, raw in (("phone", payload.phone), ("email", payload.email)):
        if raw:
            db.add(
                ContactPoint(
                    customer_id=customer.id,
                    channel=channel,
                    value=normalize_value(channel, str(raw)),
                    is_primary=True,
                )
            )

    await db.commit()
    return await _get_customer(db, customer.id)


async def _sync_contact_point(
    db: AsyncSession,
    customer_id: UUID,
    channel: str,
    old_value: Optional[str],
    new_value: Optional[str],
) -> None:
    """Телефон/email в карточке — основной контакт канала, держим contact_point в согласии."""
    if not new_value or new_value == old_value:
        return
    value = normalize_value(channel, new_value)

    # Старый контакт обновляем на новое значение, если оно никем не занято
    if old_value:
        old_norm = normalize_value(channel, old_value)
        existing = (
            await db.execute(
                select(ContactPoint).where(
                    ContactPoint.customer_id == customer_id,
                    ContactPoint.channel == channel,
                    ContactPoint.value == old_norm,
                )
            )
        ).scalars().first()
        if existing:
            taken = (
                await db.execute(
                    select(ContactPoint.id).where(
                        ContactPoint.customer_id == customer_id,
                        ContactPoint.channel == channel,
                        ContactPoint.value == value,
                        ContactPoint.id != existing.id,
                    )
                )
            ).scalars().first()
            if not taken:
                existing.value = value
                return

    taken = (
        await db.execute(
            select(ContactPoint.id).where(
                ContactPoint.customer_id == customer_id,
                ContactPoint.channel == channel,
                ContactPoint.value == value,
            )
        )
    ).scalars().first()
    if taken:
        return

    has_channel = (
        await db.execute(
            select(ContactPoint.id).where(
                ContactPoint.customer_id == customer_id,
                ContactPoint.channel == channel,
            )
        )
    ).scalars().first()
    db.add(
        ContactPoint(
            customer_id=customer_id,
            channel=channel,
            value=value,
            is_primary=not has_channel,
        )
    )


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = await db.get(Customer, customer_id)
    if not customer or customer.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    old_phone, old_email = customer.phone, customer.email
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)

    if "phone" in payload.model_fields_set:
        await _sync_contact_point(db, customer_id, "phone", old_phone, customer.phone)
    if "email" in payload.model_fields_set:
        await _sync_contact_point(db, customer_id, "email", old_email, customer.email)

    await db.commit()
    return await _get_customer(db, customer_id)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Скрывает карточку: переписка, документы, история и статистика сохраняются."""
    customer = await db.get(Customer, customer_id)
    if not customer or customer.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    from datetime import datetime, timezone

    customer.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return None


# ------------------------------------------------------------------
# Сканы документов
# ------------------------------------------------------------------

@router.post(
    "/{customer_id}/documents",
    response_model=CustomerDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    customer_id: UUID,
    file: UploadFile = File(...),
    kind: CustomerDocumentType = Form(CustomerDocumentType.PASSPORT_RF),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = await db.get(Customer, customer_id)
    if not customer or customer.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    ext = ALLOWED_DOC_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(
            status_code=415,
            detail="Поддерживаются JPG, PNG, WEBP и PDF",
        )

    payload = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"Файл больше {settings.MAX_UPLOAD_MB} МБ"
        )

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    filename = f"customer-{customer_id}-{uuid4hex()}{ext}"
    with open(os.path.join(settings.UPLOAD_DIR, filename), "wb") as fh:
        fh.write(payload)

    document = CustomerDocument(
        customer_id=customer_id,
        kind=kind,
        file_url=f"/uploads/{filename}",
        original_name=file.filename,
        content_type=file.content_type,
        size=len(payload),
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document


def uuid4hex() -> str:
    from uuid import uuid4

    return uuid4().hex[:12]


@router.delete(
    "/{customer_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    customer_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CustomerDocument).where(
            CustomerDocument.id == document_id,
            CustomerDocument.customer_id == customer_id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    path = os.path.join(settings.UPLOAD_DIR, os.path.basename(document.file_url))
    if os.path.exists(path):
        os.remove(path)

    await db.delete(document)
    await db.commit()
    return None
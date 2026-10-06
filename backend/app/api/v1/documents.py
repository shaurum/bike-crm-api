import os

from fastapi import (
    APIRouter,
    Depends,
    Query,
    HTTPException,
    UploadFile,
    File,
    Form,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID

from app.core.config import settings
from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models import (
    Bike,
    CompanyProfile,
    Customer,
    Document,
    DocumentKind,
    DocumentStatus,
    Lead,
    User,
)
from app.schemas.crm import (
    DocumentResponse,
    DocumentListResponse,
    DocumentGenerateRequest,
    CompanyProfileResponse,
    CompanyProfileUpdate,
)
from app.services import documents as doc_service

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_DOC_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    kind: Optional[DocumentKind] = None,
    doc_status: Optional[DocumentStatus] = Query(None, alias="status"),
    customer_id: Optional[UUID] = None,
    lead_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Document).options(
        selectinload(Document.customer), selectinload(Document.bike)
    )

    if kind:
        query = query.where(Document.kind == kind)
    if doc_status:
        query = query.where(Document.status == doc_status)
    if customer_id:
        query = query.where(Document.customer_id == customer_id)
    if lead_id:
        query = query.where(Document.lead_id == lead_id)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = (
        query.order_by(Document.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    result = await db.execute(query)
    items = []
    for doc in result.scalars().all():
        doc.bike_name = doc.bike.model if doc.bike else None
        items.append(doc)

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/company", response_model=CompanyProfileResponse)
async def get_company(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    company = (
        await db.execute(select(CompanyProfile).order_by(CompanyProfile.created_at))
    ).scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Реквизиты арендодателя не заданы")
    return company


@router.patch("/company", response_model=CompanyProfileResponse)
async def update_company(
    payload: CompanyProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    company = (
        await db.execute(select(CompanyProfile).order_by(CompanyProfile.created_at))
    ).scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Реквизиты арендодателя не заданы")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value)

    await db.commit()
    await db.refresh(company)
    return company


@router.post(
    "/generate", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED
)
async def generate_document(
    payload: DocumentGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Формирует PDF-договор из данных сделки."""
    if not payload.lead_id:
        raise HTTPException(status_code=400, detail="Укажите сделку")

    lead = await db.get(Lead, payload.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Сделка не найдена")

    customer = (
        await db.get(Customer, lead.customer_id) if lead.customer_id else None
    )
    bike = await db.get(Bike, lead.bike_id) if lead.bike_id else None
    if bike is not None:
        bike = (
            await db.execute(
                select(Bike).options(selectinload(Bike.prices)).where(Bike.id == bike.id)
            )
        ).scalar_one()

    company = (
        await db.execute(select(CompanyProfile).order_by(CompanyProfile.created_at))
    ).scalars().first()

    count = await db.scalar(select(func.count()).select_from(Document.__table__))
    number = doc_service.next_document_number(count or 0)

    context = doc_service.build_contract_context(lead, customer, bike, company, number)

    if not payload.allow_incomplete:
        missing = doc_service.missing_fields(context)
        if missing:
            raise HTTPException(
                status_code=409,
                detail="Не заполнено: " + ", ".join(missing),
            )

    pdf = doc_service.render_contract_pdf(context)

    filename = f"contract-{lead.id}-{number}.pdf"
    file_url, size = doc_service.save_pdf(pdf, filename)

    document = Document(
        customer_id=lead.customer_id,
        lead_id=lead.id,
        bike_id=lead.bike_id,
        kind=DocumentKind.CONTRACT_RENTAL,
        status=DocumentStatus.ISSUED,
        number=number,
        issued_at=lead.rental_start_at,
        file_url=file_url,
        original_name=f"Договор аренды {number}.pdf",
        size=size,
        payload={
            "context": context,
            "incomplete": doc_service.missing_fields(context),
        },
    )
    db.add(document)
    await db.commit()

    result = await db.execute(
        select(Document)
        .options(selectinload(Document.customer), selectinload(Document.bike))
        .where(Document.id == document.id)
    )
    doc = result.scalar_one()
    doc.bike_name = doc.bike.model if doc.bike else None
    return doc


@router.post(
    "", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED
)
async def upload_scan(
    file: UploadFile = File(...),
    customer_id: Optional[UUID] = Form(None),
    lead_id: Optional[UUID] = Form(None),
    number: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Загрузка подписанного скана."""
    ext = ALLOWED_DOC_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(
            status_code=415, detail="Поддерживаются JPG, PNG, WEBP и PDF"
        )

    payload = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"Файл больше {settings.MAX_UPLOAD_MB} МБ"
        )

    if customer_id and not await db.get(Customer, customer_id):
        raise HTTPException(status_code=404, detail="Клиент не найден")

    from uuid import uuid4

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    filename = f"doc-{uuid4().hex[:12]}{ext}"
    with open(os.path.join(settings.UPLOAD_DIR, filename), "wb") as fh:
        fh.write(payload)

    document = Document(
        customer_id=customer_id,
        lead_id=lead_id,
        kind=DocumentKind.SCAN,
        status=DocumentStatus.SIGNED,
        number=number,
        file_url=f"/uploads/{filename}",
        original_name=file.filename,
        size=len(payload),
        payload={},
    )
    db.add(document)
    await db.commit()

    result = await db.execute(
        select(Document)
        .options(selectinload(Document.customer), selectinload(Document.bike))
        .where(Document.id == document.id)
    )
    return result.scalar_one()


@router.patch("/{document_id}/status", response_model=DocumentResponse)
async def change_status(
    document_id: UUID,
    doc_status: DocumentStatus,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    document.status = doc_status
    await db.commit()

    result = await db.execute(
        select(Document)
        .options(selectinload(Document.customer), selectinload(Document.bike))
        .where(Document.id == document_id)
    )
    return result.scalar_one()


@router.post("/{document_id}/signed", response_model=DocumentResponse)
async def attach_signed_scan(
    document_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Прикладывает подписанный скан к документу."""
    from datetime import datetime, timezone

    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    ext = ALLOWED_DOC_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(
            status_code=415, detail="Поддерживаются JPG, PNG, WEBP и PDF"
        )

    payload = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"Файл больше {settings.MAX_UPLOAD_MB} МБ"
        )

    # Заменяем предыдущий скан, чтобы не плодить файлы
    if document.signed_file_url:
        old = os.path.join(settings.UPLOAD_DIR, os.path.basename(document.signed_file_url))
        if os.path.exists(old):
            os.remove(old)

    from uuid import uuid4

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    filename = f"signed-{document.id}-{uuid4().hex[:8]}{ext}"
    with open(os.path.join(settings.UPLOAD_DIR, filename), "wb") as fh:
        fh.write(payload)

    document.signed_file_url = f"/uploads/{filename}"
    document.signed_original_name = file.filename
    document.signed_at = datetime.now(timezone.utc)
    document.signed_size = len(payload)

    if document.status == DocumentStatus.DRAFT:
        document.status = DocumentStatus.ISSUED
    if document.status == DocumentStatus.ISSUED:
        document.status = DocumentStatus.SIGNED

    await db.commit()

    result = await db.execute(
        select(Document)
        .options(selectinload(Document.customer), selectinload(Document.bike))
        .where(Document.id == document.id)
    )
    doc = result.scalar_one()
    doc.bike_name = doc.bike.model if doc.bike else None
    return doc


@router.delete("/{document_id}/signed", response_model=DocumentResponse)
async def detach_signed_scan(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    if document.signed_file_url:
        path = os.path.join(
            settings.UPLOAD_DIR, os.path.basename(document.signed_file_url)
        )
        if os.path.exists(path):
            os.remove(path)

    document.signed_file_url = None
    document.signed_original_name = None
    document.signed_at = None
    document.signed_size = None
    document.status = DocumentStatus.ISSUED

    await db.commit()

    result = await db.execute(
        select(Document)
        .options(selectinload(Document.customer), selectinload(Document.bike))
        .where(Document.id == document.id)
    )
    doc = result.scalar_one()
    doc.bike_name = doc.bike.model if doc.bike else None
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    for url in (document.file_url, document.signed_file_url):
        if url:
            path = os.path.join(settings.UPLOAD_DIR, os.path.basename(url))
            if os.path.exists(path):
                os.remove(path)

    await db.delete(document)
    await db.commit()
    return None
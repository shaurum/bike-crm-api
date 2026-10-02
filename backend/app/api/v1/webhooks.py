from fastapi import APIRouter, Depends, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.core.database import get_db
from app.models import Lead, LeadSource, LeadStatus
from app.core.config import settings

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def get_source_by_type(source_type: str, db: AsyncSession):
    result = await db.execute(
        select(LeadSource).where(LeadSource.type == source_type, LeadSource.is_active == True)
    )
    return result.scalar_one_or_none()


@router.post("/avito")
async def avito_webhook(
    request: Request,
    x_avito_signature: str = Header(None),
    db: AsyncSession = Depends(get_db),
):
    payload = await request.json()
    source = await get_source_by_type("avito", db)
    if not source:
        raise HTTPException(status_code=404, detail="Источник Авито не настроен")

    from app.tasks.webhooks import process_avito_webhook
    process_avito_webhook.delay(str(source.id), payload)
    return {"status": "accepted"}


@router.post("/vk")
async def vk_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    payload = await request.json()
    source = await get_source_by_type("vk", db)
    if not source:
        raise HTTPException(status_code=404, detail="Источник VK не настроен")

    if payload.get("type") == "confirmation":
        return {"confirmation_token": source.config.get("confirmation_token", "")}

    from app.tasks.webhooks import process_vk_webhook
    process_vk_webhook.delay(str(source.id), payload)
    return {"status": "accepted"}


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    payload = await request.json()
    source = await get_source_by_type("telegram", db)
    if not source:
        raise HTTPException(status_code=404, detail="Источник Telegram не настроен")

    from app.tasks.webhooks import process_telegram_webhook
    process_telegram_webhook.delay(str(source.id), payload)
    return {"status": "accepted"}


@router.post("/email")
async def email_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    payload = await request.json()
    source = await get_source_by_type("email", db)
    if not source:
        raise HTTPException(status_code=404, detail="Источник Email не настроен")

    from app.tasks.webhooks import process_email_webhook
    process_email_webhook.delay(str(source.id), payload)
    return {"status": "accepted"}
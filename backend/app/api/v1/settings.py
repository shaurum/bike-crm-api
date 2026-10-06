"""Раздел настроек: реквизиты арендодателя, интеграции, профиль и пароль."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.config import settings as app_settings
from app.core.database import get_db
from app.core.security import get_password_hash, verify_password
from app.models import CompanyProfile, IntegrationSetting, User
from app.schemas.settings import (
    CompanyProfileResponse,
    CompanyProfileUpdate,
    EmailSettings,
    EmailSettingsResponse,
    EmailSettingsUpdate,
    EmailTestRequest,
    IntegrationSummary,
    SettingsBundle,
)
from app.schemas.rental import PasswordChange, UserProfileUpdate, UserResponse
from app.services.mail import MailError, get_mail_settings, send_email

logger = logging.getLogger(__name__)

router = APIRouter()

# Поля, которые считаются «интеграция настроена»
REQUIRED_FIELDS = {
    "email": ["from_email"],
    "telegram": [],
    "avito": [],
    "vk": [],
    "widget": [],
}

# Какие секреты показывать как «уже заданы»
SECRET_FIELDS = {
    "email": ["password", "api_key"],
}


async def _get_company(db: AsyncSession) -> Optional[CompanyProfile]:
    return (
        await db.execute(select(CompanyProfile).order_by(CompanyProfile.created_at))
    ).scalars().first()


def _to_summary(item: IntegrationSetting) -> IntegrationSummary:
    """Готовит интеграцию к выдаче, не раскрывая секреты."""
    config = item.config or {}
    secret = item.secret or {}
    required = REQUIRED_FIELDS.get(item.name, [])
    configured = all(bool(config.get(field)) for field in required) if required else False
    # Секрет считается заданным, если поле есть и непустое
    present = [field for field in SECRET_FIELDS.get(item.name, []) if secret.get(field)]

    return IntegrationSummary(
        id=item.id,
        name=item.name,
        title=item.title,
        is_enabled=item.is_enabled,
        is_configured=configured,
        secret_fields=present,
        updated_at=item.updated_at,
    )


@router.get("", response_model=SettingsBundle)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Всё для экрана настроек одним запросом."""
    company = await _get_company(db)
    items = (
        await db.execute(select(IntegrationSetting).order_by(IntegrationSetting.name))
    ).scalars().all()

    return SettingsBundle(
        company=CompanyProfileResponse.model_validate(company) if company else None,
        integrations=[_to_summary(item) for item in items],
    )


# --- Реквизиты арендодателя ---


@router.get("/company", response_model=CompanyProfileResponse)
async def get_company_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    company = await _get_company(db)
    if not company:
        raise HTTPException(status_code=404, detail="Реквизиты арендодателя не заданы")
    return company


@router.patch("/company", response_model=CompanyProfileResponse)
async def update_company_settings(
    payload: CompanyProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Правка реквизитов, которые подставляются в договоры."""
    company = await _get_company(db)
    if not company:
        raise HTTPException(status_code=404, detail="Реквизиты арендодателя не заданы")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value)

    await db.commit()
    await db.refresh(company)
    return company


# --- Интеграции ---


@router.get("/integrations", response_model=list[IntegrationSummary])
async def list_integrations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = (
        await db.execute(select(IntegrationSetting).order_by(IntegrationSetting.name))
    ).scalars().all()
    return [_to_summary(item) for item in items]


async def _get_integration(db: AsyncSession, name: str) -> IntegrationSetting:
    item = (
        await db.execute(select(IntegrationSetting).where(IntegrationSetting.name == name))
    ).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail=f"Интеграция «{name}» не найдена")
    return item


@router.get("/integrations/email", response_model=EmailSettingsResponse)
async def get_email_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Настройки почты. Секреты не возвращаются, только признаки."""
    item = await _get_integration(db, "email")
    config = item.config or {}
    secret = item.secret or {}

    return EmailSettingsResponse(
        is_enabled=item.is_enabled,
        config=EmailSettings(
            provider=config.get("provider") or "smtp",
            host=config.get("host") or None,
            port=int(config.get("port") or 587),
            username=config.get("username") or None,
            from_email=config.get("from_email") or None,
            from_name=config.get("from_name") or None,
            use_tls=bool(config.get("use_tls", True)),
            imap_host=config.get("imap_host") or None,
            imap_port=int(config.get("imap_port") or 993),
            imap_username=config.get("imap_username") or None,
            imap_use_ssl=bool(config.get("imap_use_ssl", True)),
            imap_folder=config.get("imap_folder") or "INBOX",
        ),
        password_set=bool(secret.get("password")),
        api_key_set=bool(secret.get("api_key")),
        imap_password_set=bool(secret.get("imap_password")),
        from_env=not item.is_enabled,
        imap_ready=bool(
            item.is_enabled
            and config.get("imap_host")
            and (config.get("imap_username") or config.get("from_email"))
            and (
                secret.get("imap_password")
                or config.get("imap_username") == config.get("from_email")
            )
        ),
        updated_at=item.updated_at,
    )


@router.patch("/integrations/email", response_model=EmailSettingsResponse)
async def update_email_settings(
    payload: EmailSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Сохраняет настройки почты.

    Пустая строка в пароле или ключе означает «оставить прежнее»,
    поэтому сбросить секрет нельзя случайно.
    """
    item = await _get_integration(db, "email")

    config = dict(item.config or {})
    secret = dict(item.secret or {})

    incoming = payload.config.model_dump()

    # Секреты меняем только если реально пришли непустыми
    for field in ("password", "api_key", "imap_password"):
        value = getattr(payload, field)
        if value:
            secret[field] = value

    config.update(incoming)

    item.config = config
    item.secret = secret
    item.is_enabled = payload.is_enabled

    await db.commit()
    await db.refresh(item)

    return await get_email_settings(db=db, current_user=current_user)


@router.post("/integrations/email/test")
async def test_email(
    payload: EmailTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Проверяет настройки, отправляя тестовое письмо."""
    mail = await get_mail_settings(db)

    if not mail.is_ready():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Почта не настроена: укажите адрес отправителя "
                + ("и API-ключ" if mail.provider == "resend" else "и хост SMTP")
            ),
        )

    subject = payload.subject or "Проверка почты — ВЖУХ и поехали"
    text = (
        "Это тестовое письмо из CRM «ВЖУХ и поехали».\n\n"
        "Если вы его получили, настройки почты работают корректно."
    )

    try:
        await send_email(db, payload.to_email, subject, text, mail=mail)
    except MailError as exc:
        logger.warning("Тестовое письмо не отправлено: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return {"ok": True, "detail": f"Письмо отправлено на {payload.to_email}"}


# --- Аккаунт ---


@router.get("/account", response_model=UserResponse)
async def get_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.patch("/account", response_model=UserResponse)
async def update_account(
    payload: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Правка собственного профиля: имя, телефон, Telegram."""
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/account/password")
async def change_password(
    payload: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Смена пароля с проверкой текущего."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Текущий пароль указан неверно"
        )

    if len(payload.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Новый пароль должен быть не короче 8 символов",
        )

    current_user.hashed_password = get_password_hash(payload.new_password)
    await db.commit()

    return {"ok": True, "detail": "Пароль обновлён"}
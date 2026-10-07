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
    AvitoCallbackRequest,
    AvitoConnectUrlResponse,
    AvitoSettings,
    AvitoSettingsResponse,
    AvitoSettingsUpdate,
    CompanyProfileResponse,
    CompanyProfileUpdate,
    EmailSettings,
    EmailSettingsResponse,
    EmailSettingsUpdate,
    EmailTestRequest,
    IntegrationSummary,
    SettingsBundle,
)
from app.services import avito as avito_service
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


async def _avito_response(item: IntegrationSetting) -> AvitoSettingsResponse:
    config = item.config or {}
    secret = item.secret or {}
    client_id = bool(secret.get("client_id"))
    client_secret = bool(secret.get("client_secret"))
    return AvitoSettingsResponse(
        is_enabled=item.is_enabled,
        config=AvitoSettings(
            redirect_uri=config.get("redirect_uri"),
            scopes=config.get("scopes")
            or "messenger:read,messenger:write,user:read",
        ),
        client_id_set=client_id,
        client_secret_set=client_secret,
        connected=bool(secret.get("access_token")),
        user_id=config.get("user_id"),
        account_name=config.get("account_name"),
        account_phone=config.get("account_phone"),
        token_expires_at=config.get("token_expires_at"),
        connected_at=config.get("connected_at"),
        ready_to_connect=bool(client_id and client_secret and config.get("redirect_uri")),
        updated_at=item.updated_at,
    )


async def _gateway_avito_response() -> AvitoSettingsResponse:
    """Настройки Авито, когда их обслуживает облачный шлюз."""
    from app.services import gateway

    try:
        data = await gateway.get_status()
    except gateway.GatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    av = data.get("avito") or {}
    configured = bool(av.get("configured"))
    connected = bool(av.get("connected"))
    return AvitoSettingsResponse(
        is_enabled=connected,
        config=AvitoSettings(redirect_uri=av.get("redirect_uri")),
        client_id_set=configured,
        client_secret_set=configured,
        connected=connected,
        user_id=av.get("user_id"),
        account_name=av.get("account_name"),
        account_phone=av.get("account_phone"),
        token_expires_at=av.get("token_expires_at"),
        connected_at=None,
        ready_to_connect=configured and bool(av.get("redirect_uri")),
    )


def _gateway_error(exc) -> HTTPException:
    if exc.status_code in (400, 401):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.get("/integrations/avito", response_model=AvitoSettingsResponse)
async def get_avito_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Настройки интеграции с Авито. Секреты не отдаются."""
    from app.services import gateway

    if gateway.is_configured():
        return await _gateway_avito_response()
    return await _avito_response(await _get_integration(db, "avito"))


@router.patch("/integrations/avito", response_model=AvitoSettingsResponse)
async def update_avito_settings(
    payload: AvitoSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Сохранение реквизитов приложения Авито."""
    item = await _get_integration(db, "avito")

    config = dict(item.config or {})
    secret = dict(item.secret or {})
    config.update(payload.config.model_dump())
    if payload.client_id:
        secret["client_id"] = payload.client_id.strip()
    if payload.client_secret:
        secret["client_secret"] = payload.client_secret.strip()

    item.config = config
    item.secret = secret
    await db.commit()
    await db.refresh(item)

    from app.services import gateway

    if gateway.is_configured():
        patch: dict = {}
        if payload.config.redirect_uri:
            patch["redirect_uri"] = payload.config.redirect_uri
        if payload.config.scopes:
            patch["scopes"] = payload.config.scopes
        if payload.client_id:
            patch["client_id"] = payload.client_id.strip()
        if payload.client_secret:
            patch["client_secret"] = payload.client_secret.strip()
        if patch:
            try:
                await gateway.avito_config(patch)
            except gateway.GatewayError as exc:
                raise _gateway_error(exc) from exc
        return await _gateway_avito_response()

    return await _avito_response(item)


@router.post("/integrations/avito/connect-url", response_model=AvitoConnectUrlResponse)
async def avito_connect_url(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ссылка, по которой владелец подтверждает доступ к своему аккаунту."""
    from app.services import gateway

    if gateway.is_configured():
        try:
            data = await gateway.avito_connect_url()
        except gateway.GatewayError as exc:
            raise _gateway_error(exc) from exc
        return AvitoConnectUrlResponse(
            url=str(data.get("url") or ""),
            redirect_uri=str(data.get("redirect_uri") or ""),
        )

    item = await _get_integration(db, "avito")
    secret = item.secret or {}
    config = item.config or {}

    if not secret.get("client_id") or not secret.get("client_secret"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сначала сохраните client_id и client_secret приложения",
        )
    redirect_uri = config.get("redirect_uri")
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сначала сохраните redirect_uri приложения",
        )
    if not str(redirect_uri).startswith("https://"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Авито принимает только redirect_uri по https",
        )

    return AvitoConnectUrlResponse(
        url=avito_service.build_connect_url(
            str(secret["client_id"]),
            str(redirect_uri),
            str(config.get("scopes") or avito_service.DEFAULT_SCOPES),
        ),
        redirect_uri=str(redirect_uri),
    )


@router.post("/integrations/avito/callback", response_model=AvitoSettingsResponse)
async def avito_callback(
    payload: AvitoCallbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Меняет код авторизации на токены и запоминает аккаунт."""
    from app.services import gateway

    if gateway.is_configured():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Подключением Авито управляет шлюз: подтвердите доступ на его "
                "странице, затем обновите настройки"
            ),
        )

    try:
        item = await avito_service.exchange_code(db, payload.code)
        account = await avito_service.fetch_account(db)
        item = await avito_service.save_account(db, account)
    except avito_service.AvitoError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return await _avito_response(item)


@router.post("/integrations/avito/disconnect", response_model=AvitoSettingsResponse)
async def avito_disconnect(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отзываем доступ: токены удаляются, реквизиты приложения остаются."""
    from app.services import gateway

    if gateway.is_configured():
        try:
            await gateway.avito_disconnect()
        except gateway.GatewayError as exc:
            raise _gateway_error(exc) from exc
        return await _gateway_avito_response()

    item = await _get_integration(db, "avito")

    secret = dict(item.secret or {})
    config = dict(item.config or {})
    for key in ("access_token", "refresh_token"):
        secret.pop(key, None)
    for key in (
        "user_id",
        "account_name",
        "account_phone",
        "token_expires_at",
        "connected_at",
    ):
        config.pop(key, None)

    item.secret = secret
    item.config = config
    item.is_enabled = False
    await db.commit()
    await db.refresh(item)
    return await _avito_response(item)


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
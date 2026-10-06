"""Схемы настроек: интеграции и реквизиты арендодателя."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IntegrationSummary(BaseModel):
    """Список интеграций для экрана настроек.

    Секреты не раскрываются — вместо них признак `secret_fields`.
    """

    id: UUID
    name: str
    title: str
    is_enabled: bool
    is_configured: bool = Field(False, description="Заданы ли обязательные поля")
    secret_fields: List[str] = Field(default_factory=list, description="Секреты, которые уже сохранены")
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class EmailSettings(BaseModel):
    """Настройки исходящей и входящей почты.

    Секреты приходят пустыми, если их не меняли. Пустая строка означает
    «оставить как есть», поэтому чтобы сбросить секрет — передать `null`.
    """

    provider: str = Field("smtp", description="smtp или resend")
    host: Optional[str] = None
    port: int = 587
    username: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    use_tls: bool = True

    # Входящие письма забираем по IMAP
    imap_host: Optional[str] = None
    imap_port: int = 993
    imap_username: Optional[str] = None
    imap_use_ssl: bool = True
    imap_folder: str = "INBOX"

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        allowed = {"smtp", "resend"}
        if value not in allowed:
            raise ValueError(f"Провайдер должен быть одним из: {', '.join(sorted(allowed))}")
        return value


class EmailSettingsUpdate(BaseModel):
    is_enabled: bool = False
    config: EmailSettings
    password: Optional[str] = Field(None, description="Новый пароль SMTP; null — не менять")
    api_key: Optional[str] = Field(None, description="Новый API-ключ Resend; null — не менять")
    imap_password: Optional[str] = Field(
        None, description="Новый пароль IMAP; null — не менять"
    )


class EmailSettingsResponse(BaseModel):
    """Ответ с настройками почты. Секреты — только признаки."""

    is_enabled: bool
    config: EmailSettings
    password_set: bool = False
    api_key_set: bool = False
    imap_password_set: bool = False
    from_env: bool = Field(
        False, description="Настройки берутся из переменных окружения, а не из CRM"
    )
    imap_ready: bool = Field(
        False, description="Настроен ли приём входящих писем"
    )
    updated_at: Optional[datetime] = None


class EmailTestRequest(BaseModel):
    to_email: str
    subject: Optional[str] = None


class CompanyProfileUpdate(BaseModel):
    """Реквизиты арендодателя для договоров."""

    name: str
    ogrnip: Optional[str] = None
    inn: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    return_address: Optional[str] = None
    age_restriction: Optional[str] = None
    deposit_return: Optional[str] = None
    photo_consent: Optional[str] = None


class CompanyProfileResponse(CompanyProfileUpdate):
    id: UUID
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SettingsBundle(BaseModel):
    """Всё для экрана настроек одним запросом."""

    company: Optional[CompanyProfileResponse] = None
    integrations: List[IntegrationSummary] = Field(default_factory=list)
"""Отправка писем.

Настройки берутся из таблицы `integration_setting` (то есть из интерфейса),
а если интеграция выключена или ничего не задано — откатываемся на .env,
чтобы рабочее окружение не ломалось.
"""

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.integration import IntegrationSetting

logger = logging.getLogger(__name__)


class MailError(Exception):
    """Не удалось отправить письмо."""


@dataclass
class MailSettings:
    """Готовые к использованию параметры отправки."""

    provider: str
    from_email: str
    from_name: Optional[str] = None
    host: Optional[str] = None
    port: int = 587
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    use_tls: bool = True
    from_env: bool = False

    def is_ready(self) -> bool:
        """Хватает ли данных для отправки."""
        if not self.from_email:
            return False
        if self.provider == "resend":
            return bool(self.api_key)
        return bool(self.host)


def _parse_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


async def _get_email_row(db: AsyncSession) -> Optional[IntegrationSetting]:
    """Читает запись интеграции почты."""
    result = await db.execute(
        select(IntegrationSetting).where(IntegrationSetting.name == "email")
    )
    return result.scalars().first()


async def get_mail_settings(db: AsyncSession) -> MailSettings:
    """Собирает настройки почты: сначала из БД, затем из .env."""
    row = await _get_email_row(db)
    if row and row.is_enabled:
        cfg = row.config or {}
        secret = row.secret or {}
        from_env = False
    else:
        cfg = {}
        secret = {}
        from_env = True

    provider = cfg.get("provider") or settings.EMAIL_PROVIDER or "smtp"

    return MailSettings(
        provider=provider,
        from_email=(
            cfg.get("from_email")
            or settings.EMAIL_FROM
            or ""
        ),
        from_name=cfg.get("from_name") or None,
        host=cfg.get("host") or settings.SMTP_HOST,
        port=int(cfg.get("port") or settings.SMTP_PORT or 587),
        username=cfg.get("username") or settings.SMTP_USER,
        # Пароль из БД имеет приоритет, иначе — из окружения
        password=secret.get("password") or settings.SMTP_PASSWORD,
        api_key=secret.get("api_key") or settings.RESEND_API_KEY,
        use_tls=_parse_bool(cfg.get("use_tls"), True),
        from_env=from_env,
    )


async def _send_via_resend(mail: MailSettings, to: str, subject: str, text: str) -> None:
    """Отправка через API Resend."""
    payload = {
        "from": formataddr((mail.from_name, mail.from_email)) if mail.from_name else mail.from_email,
        "to": [to],
        "subject": subject,
        "text": text,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={"Authorization": f"Bearer {mail.api_key}"},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise MailError(f"Resend вернул ошибку: {exc}") from exc


async def _send_via_smtp(mail: MailSettings, to: str, subject: str, text: str) -> None:
    """Отправка через SMTP с поддержкой STARTTLS и SSL."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = (
        formataddr((mail.from_name, mail.from_email)) if mail.from_name else mail.from_email
    )
    message["To"] = to
    message.set_content(text)

    port = mail.port
    use_ssl = port == 465

    def _send() -> None:
        with smtplib.SMTP_SSL(mail.host, port, timeout=20) if use_ssl else smtplib.SMTP(
            mail.host, port, timeout=20
        ) as server:
            if not use_ssl and mail.use_tls:
                server.starttls()
            if mail.username and mail.password:
                server.login(mail.username, mail.password)
            server.send_message(message)

    try:
        await _run_in_threadpool(_send)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"Не удалось подключиться к SMTP-серверу: {exc}") from exc


async def send_email(
    db: AsyncSession,
    to: str,
    subject: str,
    text: str,
    mail: Optional[MailSettings] = None,
) -> None:
    """Отправляет письмо, выбирая транспорт по настройкам."""
    mail = mail or await get_mail_settings(db)

    if not mail.is_ready():
        raise MailError(
            "Почта не настроена: укажите адрес отправителя и ключ доступа в разделе настроек"
        )

    if mail.provider == "resend":
        await _send_via_resend(mail, to, subject, text)
    else:
        await _send_via_smtp(mail, to, subject, text)

    logger.info("Письмо отправлено на %s через %s", to, mail.provider)


async def _run_in_threadpool(func):
    """Синхронный SMTP-код выполняем в пуле потоков, чтобы не блокировать event loop."""
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(func)
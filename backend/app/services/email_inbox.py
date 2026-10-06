"""Приём входящих писем по IMAP.

Каждое письмо превращается в сообщение в чате клиента через
`ingest_inbound` — тот же путь, что и для вебхука.

Ключи UID последнего прочитанного письма храним в `config.imap_last_uid`,
он не секретный.
"""

import email as email_lib
import imaplib
import logging
import re
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IntegrationSetting

logger = logging.getLogger(__name__)

MAX_BODY = 4000


class ImapError(Exception):
    """Не удалось прочитать почту."""


@dataclass
class ImapSettings:
    host: str
    port: int
    username: str
    password: str
    use_ssl: bool = True
    folder: str = "INBOX"
    last_uid: int = 0

    @property
    def is_ready(self) -> bool:
        return bool(self.host and self.username and self.password)


async def get_imap_settings(db: AsyncSession) -> Optional[ImapSettings]:
    """Читает настройки IMAP из интеграции почты."""
    result = await db.execute(
        select(IntegrationSetting).where(IntegrationSetting.name == "email")
    )
    item = result.scalars().first()
    if not item or not item.is_enabled:
        return None

    config = item.config or {}
    secret = item.secret or {}
    host = config.get("imap_host")
    if not host:
        return None

    username = config.get("imap_username") or config.get("from_email") or ""
    password = secret.get("imap_password") or ""

    return ImapSettings(
        host=host,
        port=int(config.get("imap_port") or 993),
        username=username,
        password=password,
        use_ssl=bool(config.get("imap_use_ssl", True)),
        folder=config.get("imap_folder") or "INBOX",
        last_uid=int(config.get("imap_last_uid") or 0),
    )


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return value


def _body_text(msg: Message) -> str:
    """Достаём текст письма, предпочитая text/plain."""
    plain: list[str] = []
    html: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            if content_type == "text/plain" and part.get_payload(decode=True):
                plain.append(part.get_payload(decode=True).decode(errors="replace"))
            elif content_type == "text/html" and part.get_payload(decode=True):
                html.append(part.get_payload(decode=True).decode(errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            text = payload.decode(errors="replace")
            if msg.get_content_type() == "text/html":
                html.append(text)
            else:
                plain.append(text)

    if plain:
        return "\n".join(plain).strip()
    if html:
        return _strip_html("\n".join(html)).strip()
    return ""


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def fetch_new_emails(settings: ImapSettings) -> list[dict]:
    """Достаёт непрочитанные письма с сервера (синхронно)."""
    connector = (
        imaplib.IMAP4_SSL(settings.host, settings.port, timeout=30)
        if settings.use_ssl
        else imaplib.IMAP4(settings.host, settings.port, timeout=30)
    )

    try:
        try:
            connector.login(settings.username, settings.password)
        except imaplib.IMAP4.error as exc:
            raise ImapError(f"Не удалось войти на почтовый сервер: {exc}") from exc

        try:
            connector.select(settings.folder)
        except imaplib.IMAP4.error as exc:
            raise ImapError(f"Папка {settings.folder} недоступна: {exc}") from exc

        # Ищем всё после последнего прочитанного UID
        criterion = "ALL" if not settings.last_uid else f"UID {settings.last_uid + 1}:*"
        status, data = connector.uid("search", None, criterion)
        if status != "OK":
            raise ImapError("Сервер не ответил на поиск писем")

        uids = [u for u in (data[0] or b"").split() if u]
        messages: list[dict] = []

        for uid_bytes in uids:
            uid = int(uid_bytes)
            if uid <= settings.last_uid:
                continue
            status, fetched = connector.uid("fetch", uid_bytes, "(RFC822)")
            if status != "OK" or not fetched or fetched[0] is None:
                continue
            payload = fetched[0]
            if not isinstance(payload, tuple) or len(payload) < 2:
                continue

            msg = email_lib.message_from_bytes(payload[1])
            messages.append({"uid": uid, "msg": msg})

        return messages
    finally:
        try:
            connector.logout()
        except Exception:  # noqa: BLE001
            pass


def parse_email(uid: int, msg: Message) -> dict:
    """Превращает письмо в данные для ingest_inbound."""
    _, from_addr = parseaddr(msg.get("From", ""))
    from_header = _decode(msg.get("From", ""))
    name = ""
    if from_header and "<" in from_header:
        name = from_header.split("<")[0].strip().strip('"')

    subject = _decode(msg.get("Subject", ""))
    body = _body_text(msg)[:MAX_BODY]
    message_id = (msg.get("Message-ID") or "").strip() or f"imap-{uid}"

    return {
        "channel": "email",
        "sender_value": from_addr,
        "sender_name": name or None,
        "subject": subject or None,
        "content": body or f"(пустое письмо) {subject}",
        "external_msg_id": message_id,
        "meta": {"uid": uid, "subject": subject, "from": from_header},
    }
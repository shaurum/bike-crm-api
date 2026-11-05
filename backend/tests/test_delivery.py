"""П2: доставка вложений по каналам (backend).

Покрытие:
- Telegram ботом: _send_telegram_files (метод по виду файла, поле multipart,
  имя файла, caption, лимит фото 10 МБ) и _deliver (один файл + короткий текст —
  один запрос с подписью, длинный текст — отдельное сообщение);
- Telegram через шлюз: media — полные ссылки; без PUBLIC_BASE_URL очередь не вызывается;
- почта: _deliver (вложения, лимит 20 МБ — ссылки, без PUBLIC_BASE_URL — отказ),
  send_email через Resend (base64, filename) и SMTP (EmailMessage с вложением);
- Авито: полные ссылки в тексте, media в шлюз не передаётся; лимит 1000 знаков
  (обрезка текста «…», ссылки целиком, замечание, если блок ссылок длиннее лимита);
- mask_token: токен бота прячется в тексте ошибок, остальной текст не меняется;
- сквозной POST /conversations/{id}/messages для каналов telegram, email, avito.

Безопасность: внешних вызовов нет.
- httpx.AsyncClient заменяется клиентом с httpx.MockTransport, запросы записываются;
- любой реальный сетевой запрос (httpx.AsyncHTTPTransport) падает, и autouse-фикстура
  в teardown проверяет, что такого не было;
- gateway.is_configured / enqueue_outbound / resolve_telegram, mail.send_email,
  avito.load_integration / send_text и токен Telegram подменены записывающими заглушками.
  Настоящий send_email подставляется только в тестах транспортов (Resend/SMTP),
  и SMTP подменён классами, не открывающими сокет.
"""

import base64
import json
import os
import re
import smtplib
import uuid
from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import messages as messages_api
from app.core.config import settings
from app.models import ContactPoint, Conversation, Customer
from app.services import avito as avito_service
from app.services import gateway
from app.services import mail as mail_service
from app.services.attachments import mask_token, normalize_content_type, safe_name
from app.services.mail import MailError, MailSettings

# Нужно до подмены: настоящая функция отправки и настоящий клиент httpx
REAL_SEND_EMAIL = mail_service.send_email
_RealAsyncClient = httpx.AsyncClient

TOKEN = "123:TEST-TOKEN"
CHAT = "100500"
PUBLIC = "https://crm.example.ru"
PDF = b"%PDF-1.4 test"
EMAIL = "client@example.com"
CONVERSATIONS_URL = "/api/v1/conversations"
RESEND_URL = "https://api.resend.com/emails"
NO_PUBLIC_NOTE = "Вложения не отправлены: в .env не задан PUBLIC_BASE_URL"


# --- Фикстуры изоляции -------------------------------------------------------


@pytest.fixture
def rec() -> SimpleNamespace:
    """Журнал вызовов заглушек внешних сервисов."""
    return SimpleNamespace(enqueue=[], resolve=[], send_email=[], send_text=[], load_integration=[])


class _NetLog:
    """Журнал HTTP-запросов, которые ушли через MockTransport."""

    def __init__(self) -> None:
        self.requests: List[httpx.Request] = []
        self.responder = _ok_response


def _ok_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})


def _tg_error(status: int, description: str):
    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"ok": False, "description": description})

    return responder


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch, rec: SimpleNamespace):
    """Все внешние точки подменены; UPLOAD_DIR во временной папке; реальная сеть запрещена."""
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(root))
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "")
    # GATEWAY_URL в контейнере указывает на боевой шлюз: по умолчанию шлюз «не настроен»
    monkeypatch.setattr(gateway, "is_configured", lambda: False)

    async def enqueue(chat_id, text, **kwargs):
        rec.enqueue.append({"chat_id": chat_id, "text": text, "kwargs": kwargs})
        return {}

    async def resolve(username):
        rec.resolve.append(username)
        return "777"

    async def fake_send_email(db, to, subject, text, mail=None, attachments=None):
        rec.send_email.append(
            {"to": to, "subject": subject, "text": text, "attachments": attachments}
        )

    async def fake_load_integration(db):
        rec.load_integration.append(True)
        return SimpleNamespace(config={"user_id": 42})

    async def fake_send_text(db, user_id, chat_id, text):
        rec.send_text.append({"user_id": user_id, "chat_id": chat_id, "text": text})
        return "msg-1"

    async def fake_token(db, name):
        return TOKEN

    monkeypatch.setattr(gateway, "enqueue_outbound", enqueue)
    monkeypatch.setattr(gateway, "resolve_telegram", resolve)
    monkeypatch.setattr(mail_service, "send_email", fake_send_email)
    monkeypatch.setattr(avito_service, "load_integration", fake_load_integration)
    monkeypatch.setattr(avito_service, "send_text", fake_send_text)
    monkeypatch.setattr(messages_api, "_integration_token", fake_token)

    leaked: List[str] = []

    async def no_network(self, request: httpx.Request) -> httpx.Response:
        leaked.append(str(request.url))
        raise RuntimeError(f"Реальный сетевой вызов запрещён в тестах: {request.url}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)

    yield
    assert leaked == [], f"Реальные сетевые вызовы в тесте: {leaked}"


@pytest.fixture
def net(monkeypatch) -> _NetLog:
    """httpx.AsyncClient с MockTransport: все запросы записываются, ответ — log.responder."""
    log = _NetLog()

    def handler(request: httpx.Request) -> httpx.Response:
        log.requests.append(request)
        return log.responder(request)

    transport = httpx.MockTransport(handler)

    class MockClient(_RealAsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    return log


@pytest.fixture
def upload_dir(isolated) -> Path:
    return Path(settings.UPLOAD_DIR)


@pytest.fixture
def public_base(monkeypatch) -> str:
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", PUBLIC)
    return PUBLIC


@pytest.fixture
def gateway_on(monkeypatch) -> None:
    monkeypatch.setattr(gateway, "is_configured", lambda: True)


# --- Хелперы -----------------------------------------------------------------


def _upload(root: Path, name: str, data: bytes = PDF) -> str:
    """Кладёт файл в uploads/messages/att-<hex>/ под безопасным именем, как upload_attachment."""
    ext = os.path.splitext(name)[1].lower()
    folder = f"att-{uuid.uuid4().hex}"
    filename = safe_name(name, ext)
    (root / "messages" / folder).mkdir(parents=True)
    (root / "messages" / folder / filename).write_bytes(data)
    return f"/uploads/messages/{folder}/{filename}"


def _att(url: str, name: str, content_type: Optional[str] = None, size: Optional[int] = None) -> dict:
    """Вложение в том виде, в котором его получает _deliver из send_message."""
    return {
        "url": url,
        "name": name,
        "content_type": normalize_content_type(name, content_type),
        "size": size,
    }


async def deliver(
    channel: str,
    value: str,
    content: str,
    attachments: Optional[List[dict]],
    external_id: Optional[str] = None,
) -> Optional[str]:
    """Вызов _deliver напрямую. db/current_user/conv в этих ветках не используются:
    интеграции подменены в isolated."""
    recipient = ContactPoint(channel=channel, value=value, external_id=external_id)
    return await messages_api._deliver(
        None, channel, recipient, content, None, None, attachments=attachments
    )


def _parse_multipart(request: httpx.Request) -> Tuple[Dict[str, str], Dict[str, dict]]:
    """Разбирает multipart-тело: (текстовые поля, файлы {имя поля: filename/content_type/data})."""
    boundary = re.search(r"boundary=([^;]+)", request.headers["content-type"]).group(1).strip('"')
    fields: Dict[str, str] = {}
    files: Dict[str, dict] = {}
    for raw in request.content.split(b"--" + boundary.encode()):
        if raw in (b"", b"--", b"--\r\n", b"\r\n"):
            continue
        raw = raw.removeprefix(b"\r\n").removesuffix(b"\r\n")
        head, _, body = raw.partition(b"\r\n\r\n")
        text = head.decode("utf-8")
        disposition = re.search(r"^Content-Disposition:(.*)$", text, re.M | re.I).group(1)
        field = re.search(r'(?:^|;)\s*name="([^"]*)"', disposition).group(1)
        filename = re.search(r'filename="([^"]*)"', disposition)
        if filename:
            ctype = re.search(r"^Content-Type:\s*(.+)$", text, re.M | re.I)
            files[field] = {
                "filename": filename.group(1),
                "content_type": ctype.group(1).strip() if ctype else None,
                "data": body,
            }
        else:
            fields[field] = body.decode("utf-8")
    return fields, files


def _tg(request: httpx.Request):
    """Разбирает запрос к Bot API: (метод, поля, файлы). Проверяет адрес и токен в пути."""
    assert request.url.scheme == "https"
    assert request.url.host == "api.telegram.org", str(request.url)
    method = request.url.path.rsplit("/", 1)[-1]
    assert request.url.path == f"/bot{TOKEN}/{method}", request.url.path
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        fields, files = _parse_multipart(request)
    else:
        fields, files = json.loads(request.content), {}
    return method, fields, files


def _methods(net: _NetLog) -> List[str]:
    return [_tg(r)[0] for r in net.requests]


async def _make_conv(
    db: AsyncSession, channel: str, value: str, external_id: Optional[str] = None
) -> Conversation:
    customer = Customer(full_name="Клиент доставки")
    db.add(customer)
    await db.flush()
    db.add(
        ContactPoint(
            customer_id=customer.id,
            channel=channel,
            value=value,
            external_id=external_id,
            is_primary=True,
        )
    )
    conversation = Conversation(customer_id=customer.id, status="open")
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def _upload_via_api(client: AsyncClient, auth_headers, conv_id, name: str) -> dict:
    response = await client.post(
        f"{CONVERSATIONS_URL}/{conv_id}/attachments",
        headers=auth_headers,
        files={"file": (name, PDF, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- Константы ---------------------------------------------------------------


def test_limits_and_note_match_plan():
    assert messages_api.TELEGRAM_CAPTION_LIMIT == 1024
    assert messages_api.TELEGRAM_PHOTO_LIMIT == 10 * 1024 * 1024
    assert messages_api.MAIL_ATTACH_LIMIT == 20 * 1024 * 1024
    assert messages_api.NO_PUBLIC_URL_NOTE == NO_PUBLIC_NOTE


# --- Telegram ботом: _send_telegram_files ------------------------------------

TG_METHOD_CASES = [
    ("Фото №1.jpg", "image/jpeg", "sendPhoto", "photo"),
    ("photo.png", "image/png", "sendPhoto", "photo"),
    ("anim.gif", "image/gif", "sendAnimation", "animation"),
    ("voice.ogg", "audio/ogg", "sendVoice", "voice"),
    ("voice.oga", "audio/ogg", "sendVoice", "voice"),
    ("voice.opus", "audio/ogg", "sendVoice", "voice"),
    ("song.mp3", "audio/mpeg", "sendAudio", "audio"),
    ("Запись.m4a", "audio/mp4", "sendAudio", "audio"),
    ("clip.mp4", "video/mp4", "sendVideo", "video"),
    ("clip.mov", "video/quicktime", "sendVideo", "video"),
    ("Договор №5.pdf", "application/pdf", "sendDocument", "document"),
    ("Договор.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "sendDocument", "document"),
    ("photo.heic", "image/heic", "sendDocument", "document"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name, content_type, method, key", TG_METHOD_CASES)
async def test_bot_method_and_field_by_kind(net, upload_dir, name, content_type, method, key):
    url = _upload(upload_dir, name)

    sent = await messages_api._send_telegram_files(TOKEN, CHAT, [_att(url, name, content_type)])

    assert sent == 1
    assert len(net.requests) == 1
    got_method, fields, files = _tg(net.requests[0])
    assert got_method == method
    assert fields == {"chat_id": CHAT}
    assert list(files) == [key]
    assert files[key]["filename"] == name
    assert files[key]["content_type"] == normalize_content_type(name, content_type)
    assert files[key]["data"] == PDF


@pytest.mark.asyncio
async def test_bot_caption_is_sent_with_the_file(net, upload_dir):
    name = "Договор №5.pdf"
    url = _upload(upload_dir, name)

    await messages_api._send_telegram_files(
        TOKEN, CHAT, [_att(url, name, "application/pdf")], caption="Счёт во вложении"
    )

    method, fields, files = _tg(net.requests[0])
    assert method == "sendDocument"
    assert fields["caption"] == "Счёт во вложении"
    assert files["document"]["filename"] == name


@pytest.mark.asyncio
async def test_bot_caption_only_on_first_sent_file(net, upload_dir):
    photo = _att(_upload(upload_dir, "photo.jpg"), "photo.jpg", "image/jpeg")
    doc = _att(_upload(upload_dir, "Договор.pdf"), "Договор.pdf", "application/pdf")

    sent = await messages_api._send_telegram_files(TOKEN, CHAT, [photo, doc], caption="Две штуки")

    assert sent == 2
    _, first_fields, _ = _tg(net.requests[0])
    _, second_fields, _ = _tg(net.requests[1])
    assert first_fields["caption"] == "Две штуки"
    assert "caption" not in second_fields


@pytest.mark.asyncio
async def test_bot_caption_moves_to_first_file_that_was_sent(net, upload_dir):
    missing = _att("/uploads/messages/att-none/none.pdf", "none.pdf", "application/pdf")
    present = _att(_upload(upload_dir, "Договор.pdf"), "Договор.pdf", "application/pdf")

    sent = await messages_api._send_telegram_files(TOKEN, CHAT, [missing, present], caption="Текст")

    assert sent == 1
    _, fields, _ = _tg(net.requests[0])
    assert fields["caption"] == "Текст"


@pytest.mark.asyncio
async def test_bot_without_caption_has_no_caption_field(net, upload_dir):
    url = _upload(upload_dir, "Договор.pdf")

    await messages_api._send_telegram_files(TOKEN, CHAT, [_att(url, "Договор.pdf", "application/pdf")])

    _, fields, _ = _tg(net.requests[0])
    assert "caption" not in fields


@pytest.mark.asyncio
async def test_bot_missing_file_is_skipped_and_counts_zero(net):
    sent = await messages_api._send_telegram_files(
        TOKEN,
        CHAT,
        [_att("/uploads/messages/att-none/none.pdf", "none.pdf", "application/pdf")],
        caption="x",
    )

    assert sent == 0
    assert net.requests == []


@pytest.mark.asyncio
async def test_bot_photo_over_limit_goes_as_document(net, upload_dir, monkeypatch):
    monkeypatch.setattr(messages_api, "TELEGRAM_PHOTO_LIMIT", 10)
    big = _att(_upload(upload_dir, "big.jpg", b"x" * 11), "big.jpg", "image/jpeg")
    edge = _att(_upload(upload_dir, "edge.jpg", b"x" * 10), "edge.jpg", "image/jpeg")

    await messages_api._send_telegram_files(TOKEN, CHAT, [big, edge])

    method1, _, files1 = _tg(net.requests[0])
    method2, _, files2 = _tg(net.requests[1])
    assert method1 == "sendDocument"
    assert list(files1) == ["document"]
    assert files1["document"]["filename"] == "big.jpg"
    # Ровно на лимите фото ещё уходит как фото
    assert method2 == "sendPhoto"
    assert list(files2) == ["photo"]


@pytest.mark.asyncio
async def test_bot_external_links_use_json_and_size_limit(net):
    items = [
        {
            "url": "https://cdn.example.com/a.jpg",
            "name": "a.jpg",
            "content_type": "image/jpeg",
            "size": 10 * 1024 * 1024 + 1,
        },
        {"url": "https://cdn.example.com/b.mp4", "name": "b.mp4", "content_type": "video/mp4", "size": 100},
    ]

    sent = await messages_api._send_telegram_files(TOKEN, CHAT, items, caption="Ссылки")

    assert sent == 2
    method1, body1, files1 = _tg(net.requests[0])
    assert method1 == "sendDocument"
    assert files1 == {}
    assert body1 == {"chat_id": CHAT, "document": "https://cdn.example.com/a.jpg", "caption": "Ссылки"}
    method2, body2, _ = _tg(net.requests[1])
    assert method2 == "sendVideo"
    assert body2 == {"chat_id": CHAT, "video": "https://cdn.example.com/b.mp4"}


# --- Telegram ботом: _deliver ------------------------------------------------

BOT_CHAT = "@client_delivery"


@pytest.mark.asyncio
async def test_bot_single_file_short_text_is_one_request_with_caption(net, upload_dir):
    name = "Договор №5.pdf"
    url = _upload(upload_dir, name)

    note = await deliver("telegram", BOT_CHAT, "Договор во вложении", [_att(url, name, "application/pdf")])

    assert note is None
    assert _methods(net) == ["sendDocument"]
    _, fields, files = _tg(net.requests[0])
    assert fields["chat_id"] == BOT_CHAT
    assert fields["caption"] == "Договор во вложении"
    assert files["document"]["filename"] == name


@pytest.mark.asyncio
@pytest.mark.parametrize("length, with_caption", [(1024, True), (1025, False)])
async def test_bot_caption_limit_1024_boundary(net, upload_dir, length, with_caption):
    url = _upload(upload_dir, "Договор.pdf")
    text = "а" * length

    note = await deliver("telegram", BOT_CHAT, text, [_att(url, "Договор.pdf", "application/pdf")])

    assert note is None
    if with_caption:
        assert _methods(net) == ["sendDocument"]
        assert _tg(net.requests[0])[1]["caption"] == text
    else:
        assert _methods(net) == ["sendMessage", "sendDocument"]
        assert _tg(net.requests[0])[1]["text"] == text
        assert "caption" not in _tg(net.requests[1])[1]


@pytest.mark.asyncio
async def test_bot_single_file_without_text_has_no_caption_and_no_message(net, upload_dir):
    url = _upload(upload_dir, "Договор.pdf")

    note = await deliver("telegram", BOT_CHAT, "   ", [_att(url, "Договор.pdf", "application/pdf")])

    assert note is None
    assert _methods(net) == ["sendDocument"]
    assert "caption" not in _tg(net.requests[0])[1]


@pytest.mark.asyncio
async def test_bot_two_files_send_text_then_files_without_caption(net, upload_dir):
    photo = _att(_upload(upload_dir, "photo.jpg"), "photo.jpg", "image/jpeg")
    doc = _att(_upload(upload_dir, "Договор.pdf"), "Договор.pdf", "application/pdf")

    note = await deliver("telegram", BOT_CHAT, "Два файла", [photo, doc])

    assert note is None
    assert _methods(net) == ["sendMessage", "sendPhoto", "sendDocument"]
    assert _tg(net.requests[0])[1]["text"] == "Два файла"
    for request in net.requests[1:]:
        assert "caption" not in _tg(request)[1]


@pytest.mark.asyncio
async def test_bot_long_text_with_one_file_sends_text_then_file(net, upload_dir):
    url = _upload(upload_dir, "Договор.pdf")

    await deliver("telegram", BOT_CHAT, "я" * 2000, [_att(url, "Договор.pdf", "application/pdf")])

    assert _methods(net) == ["sendMessage", "sendDocument"]
    assert "caption" not in _tg(net.requests[1])[1]


@pytest.mark.asyncio
async def test_bot_missing_file_sends_text_alone(net):
    note = await deliver(
        "telegram",
        BOT_CHAT,
        "Текст без файла",
        [_att("/uploads/messages/att-none/none.pdf", "none.pdf", "application/pdf")],
    )

    assert note is None
    assert _methods(net) == ["sendMessage"]


@pytest.mark.asyncio
async def test_bot_not_connected_returns_note_without_requests(net, upload_dir, monkeypatch):
    async def no_token(db, name):
        return None

    monkeypatch.setattr(messages_api, "_integration_token", no_token)

    note = await deliver("telegram", BOT_CHAT, "Текст", [])

    assert note == "Telegram не подключён — сообщение сохранено в истории"
    assert net.requests == []


@pytest.mark.asyncio
async def test_bot_chat_not_found_returns_hint(net, upload_dir):
    net.responder = _tg_error(400, "Bad Request: chat not found")
    url = _upload(upload_dir, "Договор.pdf")

    note = await deliver("telegram", BOT_CHAT, "Текст", [_att(url, "Договор.pdf", "application/pdf")])

    assert note is not None
    assert note.startswith("Telegram не даёт боту писать первым")


@pytest.mark.asyncio
async def test_bot_error_note_does_not_expose_bot_token(net):
    """Замечание уходит в ответ API (поле note), токен в нём быть не должен.

    httpx в raise_for_status вкладывает URL запроса (вместе с /bot<TOKEN>/) в текст исключения.
    """
    net.responder = _tg_error(500, "Internal Server Error")

    note = await deliver("telegram", BOT_CHAT, "Текст", [])

    assert note is not None
    assert note.startswith("Telegram не отправил сообщение")
    assert TOKEN not in note


# --- Telegram через шлюз -----------------------------------------------------


@pytest.mark.asyncio
async def test_gateway_media_are_full_https_links(net, upload_dir, public_base, rec, gateway_on):
    name = "Договор №5.pdf"
    url = _upload(upload_dir, name)

    note = await deliver(
        "telegram", BOT_CHAT, "Смотрите договор", [_att(url, name, "application/pdf")], external_id="555"
    )

    assert note is None
    assert net.requests == [], "при шлюзе прямых запросов к Telegram быть не должно"
    [call] = rec.enqueue
    assert call["chat_id"] == "555"
    assert call["text"] == "Смотрите договор"
    assert call["kwargs"]["source"] == "telegram"
    media = call["kwargs"]["media"]
    assert media == [f"{PUBLIC}{url}"]
    assert media[0].startswith("https://")


@pytest.mark.asyncio
async def test_gateway_media_keep_order_and_count(upload_dir, public_base, rec, gateway_on):
    first = _upload(upload_dir, "Фото.jpg")
    second = _upload(upload_dir, "Договор.pdf")

    await deliver(
        "telegram",
        BOT_CHAT,
        "Два",
        [_att(first, "Фото.jpg", "image/jpeg"), _att(second, "Договор.pdf", "application/pdf")],
        external_id="555",
    )

    assert rec.enqueue[0]["kwargs"]["media"] == [f"{PUBLIC}{first}", f"{PUBLIC}{second}"]


@pytest.mark.asyncio
async def test_gateway_without_public_base_does_not_enqueue(upload_dir, rec, gateway_on):
    url = _upload(upload_dir, "Договор.pdf")

    note = await deliver(
        "telegram", BOT_CHAT, "Текст", [_att(url, "Договор.pdf", "application/pdf")], external_id="555"
    )

    assert note == NO_PUBLIC_NOTE
    assert rec.enqueue == []


@pytest.mark.asyncio
async def test_gateway_plain_text_needs_no_public_base(rec, gateway_on):
    note = await deliver("telegram", BOT_CHAT, "Привет", [], external_id="555")

    assert note is None
    assert rec.enqueue[0]["text"] == "Привет"
    assert rec.enqueue[0]["kwargs"]["media"] is None


@pytest.mark.asyncio
async def test_gateway_empty_text_with_file_uses_placeholder(upload_dir, public_base, rec, gateway_on):
    url = _upload(upload_dir, "Договор.pdf")

    note = await deliver("telegram", BOT_CHAT, "  ", [_att(url, "Договор.pdf", "application/pdf")], external_id="555")

    assert note is None
    assert rec.enqueue[0]["text"] == "Вложение"


@pytest.mark.asyncio
async def test_gateway_resolves_username_without_external_id(rec, gateway_on, public_base):
    note = await deliver("telegram", BOT_CHAT, "Привет", [])

    assert note is None
    assert rec.resolve == ["client_delivery"]
    assert rec.enqueue[0]["chat_id"] == "777"


@pytest.mark.asyncio
async def test_gateway_error_is_reported(gateway_on, monkeypatch):
    async def boom(chat_id, text, **kwargs):
        raise gateway.GatewayError("очередь переполнена")

    monkeypatch.setattr(gateway, "enqueue_outbound", boom)

    note = await deliver("telegram", BOT_CHAT, "Привет", [], external_id="555")

    assert note == "Шлюз не принял сообщение: очередь переполнена"


# --- Почта: _deliver ---------------------------------------------------------


@pytest.mark.asyncio
async def test_email_attaches_file_with_name_and_type(rec, upload_dir):
    name = "Договор №5.pdf"
    url = _upload(upload_dir, name)

    note = await deliver("email", EMAIL, "Во вложении договор", [_att(url, name, "application/pdf")])

    assert note is None
    [mail] = rec.send_email
    assert mail["to"] == EMAIL
    assert mail["subject"] == "Ответ из CRM"
    assert mail["text"] == "Во вложении договор"
    assert mail["attachments"] == [(name, PDF, "application/pdf")]


@pytest.mark.asyncio
async def test_email_several_files_keep_order_and_types(rec, upload_dir):
    photo = _upload(upload_dir, "Фото.jpg", b"jpg-data")
    doc = _upload(upload_dir, "Договор.pdf", b"pdf-data")

    await deliver(
        "email",
        EMAIL,
        "Два файла",
        [_att(photo, "Фото.jpg", "image/jpeg"), _att(doc, "Договор.pdf", "application/pdf")],
    )

    assert rec.send_email[0]["attachments"] == [
        ("Фото.jpg", b"jpg-data", "image/jpeg"),
        ("Договор.pdf", b"pdf-data", "application/pdf"),
    ]


@pytest.mark.asyncio
async def test_email_empty_text_gets_placeholder_body(rec, upload_dir):
    url = _upload(upload_dir, "Договор.pdf")

    await deliver("email", EMAIL, "", [_att(url, "Договор.pdf", "application/pdf")])

    assert rec.send_email[0]["text"] == "Файлы во вложении"


@pytest.mark.asyncio
async def test_email_total_equal_to_limit_is_still_attached(rec, upload_dir, monkeypatch, public_base):
    monkeypatch.setattr(messages_api, "MAIL_ATTACH_LIMIT", 12)
    a = _upload(upload_dir, "a.pdf", b"x" * 6)
    b = _upload(upload_dir, "b.pdf", b"y" * 6)

    note = await deliver(
        "email", EMAIL, "Текст", [_att(a, "a.pdf", "application/pdf"), _att(b, "b.pdf", "application/pdf")]
    )

    assert note is None
    assert [item[0] for item in rec.send_email[0]["attachments"]] == ["a.pdf", "b.pdf"]
    assert rec.send_email[0]["text"] == "Текст"


@pytest.mark.asyncio
async def test_email_over_limit_sends_full_links_in_text(rec, upload_dir, monkeypatch, public_base):
    monkeypatch.setattr(messages_api, "MAIL_ATTACH_LIMIT", 11)
    a = _upload(upload_dir, "Договор №5.pdf", b"x" * 6)
    b = _upload(upload_dir, "b.pdf", b"y" * 6)

    note = await deliver(
        "email",
        EMAIL,
        "Текст",
        [_att(a, "Договор №5.pdf", "application/pdf"), _att(b, "b.pdf", "application/pdf")],
    )

    assert note is None
    [mail] = rec.send_email
    assert mail["attachments"] is None
    assert mail["text"] == (
        "Текст\n\nВложения:\n"
        f"Договор №5.pdf: {PUBLIC}{a}\n"
        f"b.pdf: {PUBLIC}{b}"
    )


@pytest.mark.asyncio
async def test_email_over_limit_without_public_base_is_refused(rec, upload_dir, monkeypatch):
    monkeypatch.setattr(messages_api, "MAIL_ATTACH_LIMIT", 5)
    url = _upload(upload_dir, "Договор.pdf", b"x" * 6)

    note = await deliver("email", EMAIL, "Текст", [_att(url, "Договор.pdf", "application/pdf")])

    assert note == "Вложения слишком большие для письма и не отправлены"
    assert rec.send_email == []


@pytest.mark.asyncio
async def test_email_mail_error_is_reported(monkeypatch):
    async def boom(db, to, subject, text, mail=None, attachments=None):
        raise MailError("SMTP недоступен")

    monkeypatch.setattr(mail_service, "send_email", boom)

    note = await deliver("email", EMAIL, "Текст", [])

    assert note == "Письмо не отправлено: SMTP недоступен"


# --- Почта: транспорты send_email --------------------------------------------


def _resend_settings() -> MailSettings:
    return MailSettings(
        provider="resend", from_email="crm@example.ru", from_name="ВЖУХ CRM", api_key="re_test_key"
    )


@pytest.mark.asyncio
async def test_resend_payload_has_base64_and_filename(net):
    await REAL_SEND_EMAIL(
        None,
        EMAIL,
        "Ответ из CRM",
        "Текст",
        mail=_resend_settings(),
        attachments=[("Договор №5.pdf", PDF, "application/pdf")],
    )

    assert len(net.requests) == 1
    request = net.requests[0]
    assert str(request.url) == RESEND_URL
    assert request.headers["authorization"] == "Bearer re_test_key"
    body = json.loads(request.content)
    assert body["to"] == [EMAIL]
    assert body["text"] == "Текст"
    [item] = body["attachments"]
    assert set(item) == {"filename", "content"}
    assert item["filename"] == "Договор №5.pdf"
    assert base64.b64decode(item["content"]) == PDF


@pytest.mark.asyncio
async def test_resend_without_attachments_has_no_field(net):
    await REAL_SEND_EMAIL(None, EMAIL, "Ответ из CRM", "Текст", mail=_resend_settings())

    assert "attachments" not in json.loads(net.requests[0].content)


@pytest.mark.asyncio
async def test_email_deliver_through_resend_attaches_file(net, upload_dir, monkeypatch):
    monkeypatch.setattr(mail_service, "send_email", REAL_SEND_EMAIL)

    async def settings_stub(db):
        return _resend_settings()

    monkeypatch.setattr(mail_service, "get_mail_settings", settings_stub)
    url = _upload(upload_dir, "Договор №5.pdf")

    note = await deliver("email", EMAIL, "Текст", [_att(url, "Договор №5.pdf", "application/pdf")])

    assert note is None
    body = json.loads(net.requests[0].content)
    assert body["subject"] == "Ответ из CRM"
    assert body["attachments"][0]["filename"] == "Договор №5.pdf"
    assert base64.b64decode(body["attachments"][0]["content"]) == PDF


def _install_smtp(monkeypatch) -> List[Any]:
    """Подменяет smtplib.SMTP и SMTP_SSL: сокетов не открывается, сообщения запоминаются."""
    servers: List[Any] = []

    def factory(kind: str):
        class FakeServer:
            def __init__(self, host, port, timeout=None):
                self.kind = kind
                self.host = host
                self.port = port
                self.started_tls = False
                self.login_args = None
                self.messages: List[EmailMessage] = []
                servers.append(self)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def starttls(self):
                self.started_tls = True

            def login(self, user, password):
                self.login_args = (user, password)

            def send_message(self, message):
                self.messages.append(message)

        return FakeServer

    monkeypatch.setattr(smtplib, "SMTP", factory("SMTP"))
    monkeypatch.setattr(smtplib, "SMTP_SSL", factory("SMTP_SSL"))
    return servers


def _smtp_settings(port: int) -> MailSettings:
    return MailSettings(
        provider="smtp",
        from_email="crm@example.ru",
        host="smtp.example.ru",
        port=port,
        use_tls=True,
        username="crm",
        password="pw",
    )


@pytest.mark.asyncio
async def test_smtp_587_starttls_message_contains_named_attachment(monkeypatch):
    servers = _install_smtp(monkeypatch)

    await REAL_SEND_EMAIL(
        None,
        EMAIL,
        "Ответ из CRM",
        "Текст письма",
        mail=_smtp_settings(587),
        attachments=[("Договор №5.pdf", PDF, "application/pdf")],
    )

    [server] = servers
    assert server.kind == "SMTP"
    assert server.started_tls is True
    assert server.login_args == ("crm", "pw")
    [msg] = server.messages
    assert isinstance(msg, EmailMessage)
    assert msg["Subject"] == "Ответ из CRM"
    assert msg["To"] == EMAIL
    attachments = list(msg.iter_attachments())
    assert len(attachments) == 1
    part = attachments[0]
    assert part.get_filename() == "Договор №5.pdf"
    assert part.get_content_type() == "application/pdf"
    assert part.get_payload(decode=True) == PDF
    assert msg.get_body(preferencelist=("plain",)).get_content().strip() == "Текст письма"


@pytest.mark.asyncio
async def test_smtp_465_uses_ssl_without_starttls(monkeypatch):
    servers = _install_smtp(monkeypatch)

    await REAL_SEND_EMAIL(
        None,
        EMAIL,
        "Ответ из CRM",
        "Текст",
        mail=_smtp_settings(465),
        attachments=[("Счёт.pdf", PDF, "application/pdf")],
    )

    [server] = servers
    assert server.kind == "SMTP_SSL"
    assert server.started_tls is False
    [part] = list(server.messages[0].iter_attachments())
    assert part.get_filename() == "Счёт.pdf"
    assert part.get_payload(decode=True) == PDF


@pytest.mark.asyncio
async def test_smtp_unknown_content_type_falls_back_to_octet_stream(monkeypatch):
    servers = _install_smtp(monkeypatch)

    await REAL_SEND_EMAIL(
        None, EMAIL, "S", "T", mail=_smtp_settings(587), attachments=[("data.bin", b"\x00\x01", "")]
    )

    [part] = list(servers[0].messages[0].iter_attachments())
    assert part.get_content_type() == "application/octet-stream"
    assert part.get_filename() == "data.bin"


# --- Авито -------------------------------------------------------------------

AVITO_CHAT = "chat-1"


@pytest.mark.asyncio
async def test_avito_direct_puts_full_links_into_text(rec, upload_dir, public_base):
    name = "Договор №5.pdf"
    url = _upload(upload_dir, name)

    note = await deliver(
        "avito", "avito-user", "Договор во вложении", [_att(url, name, "application/pdf")], external_id=AVITO_CHAT
    )

    assert note is None
    assert rec.enqueue == []
    assert rec.send_text == [
        {
            "user_id": "42",
            "chat_id": AVITO_CHAT,
            "text": f"Договор во вложении\n\n{name}: {PUBLIC}{url}",
        }
    ]


@pytest.mark.asyncio
async def test_avito_direct_without_public_base_sends_nothing(rec, upload_dir):
    url = _upload(upload_dir, "Договор.pdf")

    note = await deliver(
        "avito", "avito-user", "Текст", [_att(url, "Договор.pdf", "application/pdf")], external_id=AVITO_CHAT
    )

    assert note == NO_PUBLIC_NOTE
    assert rec.send_text == []
    assert rec.enqueue == []


@pytest.mark.asyncio
async def test_avito_gateway_gets_links_and_no_media(rec, upload_dir, public_base, gateway_on):
    name = "Договор №5.pdf"
    url = _upload(upload_dir, name)

    note = await deliver(
        "avito", "avito-user", "Договор во вложении", [_att(url, name, "application/pdf")], external_id=AVITO_CHAT
    )

    assert note is None
    assert rec.send_text == []
    [call] = rec.enqueue
    assert call["chat_id"] == AVITO_CHAT
    assert call["text"] == f"Договор во вложении\n\n{name}: {PUBLIC}{url}"
    assert "media" not in call["kwargs"]
    assert call["kwargs"] == {}


@pytest.mark.asyncio
async def test_avito_gateway_without_public_base_enqueues_nothing(rec, upload_dir, gateway_on):
    url = _upload(upload_dir, "Договор.pdf")

    note = await deliver(
        "avito", "avito-user", "Текст", [_att(url, "Договор.pdf", "application/pdf")], external_id=AVITO_CHAT
    )

    assert note == NO_PUBLIC_NOTE
    assert rec.enqueue == []


@pytest.mark.asyncio
async def test_avito_empty_text_has_only_link_lines(rec, upload_dir, public_base, gateway_on):
    url = _upload(upload_dir, "Договор №5.pdf")

    await deliver("avito", "avito-user", "", [_att(url, "Договор №5.pdf", "application/pdf")], external_id=AVITO_CHAT)

    assert rec.enqueue[0]["text"] == f"Договор №5.pdf: {PUBLIC}{url}"


@pytest.mark.asyncio
async def test_avito_two_files_one_line_each(rec, upload_dir, public_base, gateway_on):
    a = _upload(upload_dir, "a.pdf")
    b = _upload(upload_dir, "Счёт.pdf")

    await deliver(
        "avito",
        "avito-user",
        "Документы",
        [_att(a, "a.pdf", "application/pdf"), _att(b, "Счёт.pdf", "application/pdf")],
        external_id=AVITO_CHAT,
    )

    assert rec.enqueue[0]["text"] == (
        f"Документы\n\na.pdf: {PUBLIC}{a}\nСчёт.pdf: {PUBLIC}{b}"
    )


@pytest.mark.asyncio
async def test_avito_without_attachments_text_is_unchanged(rec, public_base, gateway_on):
    await deliver("avito", "avito-user", "Просто текст", [], external_id=AVITO_CHAT)

    assert rec.enqueue[0]["text"] == "Просто текст"


@pytest.mark.asyncio
async def test_avito_without_dialog_id_returns_note(rec):
    note = await deliver("avito", "avito-user", "Текст", [], external_id=None)

    assert note is not None
    assert note.startswith("Не найден идентификатор диалога Авито")
    assert rec.send_text == []
    assert rec.enqueue == []


# --- Авито: лимит текста AVITO_TEXT_LIMIT ------------------------------------

AVITO_LIMIT = messages_api.AVITO_TEXT_LIMIT
AVITO_TOO_MANY = "Слишком много вложений для Авито — отправьте их несколькими сообщениями"


@pytest.fixture(params=["gateway", "direct"])
def avito_mode(request, monkeypatch) -> str:
    """Каждый сценарий идёт дважды: через шлюз (enqueue_outbound) и напрямую (avito.send_text)."""
    if request.param == "gateway":
        monkeypatch.setattr(gateway, "is_configured", lambda: True)
    return request.param


def _avito_texts(rec: SimpleNamespace, mode: str) -> List[str]:
    """Тексты, ушедшие в выбранный режимом канал. Второй канал должен быть пуст."""
    if mode == "gateway":
        assert rec.send_text == []
        return [call["text"] for call in rec.enqueue]
    assert rec.enqueue == []
    return [call["text"] for call in rec.send_text]


def _avito_att(upload_dir: Path, name: str) -> dict:
    return _att(_upload(upload_dir, name), name, "application/pdf")


def _link_line(att: dict) -> str:
    return f"{att['name']}: {PUBLIC}{att['url']}"


def test_avito_limit_constant_is_1000():
    assert AVITO_LIMIT == 1000


@pytest.mark.asyncio
async def test_avito_long_text_is_cut_with_ellipsis_and_links_kept(rec, upload_dir, public_base, avito_mode):
    atts = [
        _avito_att(upload_dir, "Договор " + "а" * 150 + ".pdf"),
        _avito_att(upload_dir, "Акт " + "б" * 150 + ".pdf"),
    ]
    links = "\n".join(_link_line(a) for a in atts)
    # Предусловие: ссылки помещаются, а текст — нет
    assert len(links) < AVITO_LIMIT - 100
    text = "т" * 1500  # без пробелов: обрезка не теряет лишних знаков

    note = await deliver("avito", "avito-user", text, atts, external_id=AVITO_CHAT)

    assert note is None
    [out] = _avito_texts(rec, avito_mode)
    assert len(out) <= AVITO_LIMIT
    assert len(out) == AVITO_LIMIT
    assert out.endswith("\n\n" + links), "все ссылки целиком, блоком в конце"
    body = out[: -len(links) - 2]
    assert body.endswith("…")
    assert len(body) > 1, "часть текста должна остаться"
    assert text.startswith(body[:-1])


@pytest.mark.asyncio
@pytest.mark.parametrize("links_len", [997, 998, 1000])
async def test_avito_no_room_for_text_sends_only_links(rec, upload_dir, public_base, avito_mode, links_len):
    url = _upload(upload_dir, "Счёт.pdf")
    tail = f": {PUBLIC}{url}"
    att = _att(url, "а" * (links_len - len(tail) - 4) + ".pdf", "application/pdf")
    links = _link_line(att)
    assert len(links) == links_len

    note = await deliver("avito", "avito-user", "т" * 500, [att], external_id=AVITO_CHAT)

    assert note is None
    assert _avito_texts(rec, avito_mode) == [links]


@pytest.mark.asyncio
@pytest.mark.parametrize("links_len", [1001, 2000])
async def test_avito_links_block_over_limit_is_refused(rec, upload_dir, public_base, avito_mode, links_len):
    url = _upload(upload_dir, "Реестр.pdf")
    tail = f": {PUBLIC}{url}"
    att = _att(url, "я" * (links_len - len(tail) - 4) + ".pdf", "application/pdf")
    assert len(_link_line(att)) == links_len

    note = await deliver("avito", "avito-user", "Текст", [att], external_id=AVITO_CHAT)

    assert note == AVITO_TOO_MANY
    assert rec.enqueue == []
    assert rec.send_text == []


@pytest.mark.asyncio
async def test_avito_short_text_is_unchanged(rec, upload_dir, public_base, avito_mode):
    atts = [_avito_att(upload_dir, "Договор.pdf"), _avito_att(upload_dir, "Счёт.pdf")]
    links = "\n".join(_link_line(a) for a in atts)

    note = await deliver("avito", "avito-user", "Короткий текст", atts, external_id=AVITO_CHAT)

    assert note is None
    assert _avito_texts(rec, avito_mode) == [f"Короткий текст\n\n{links}"]


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [0, 1])
async def test_avito_text_at_room_boundary(rec, upload_dir, public_base, avito_mode, extra):
    att = _avito_att(upload_dir, "Договор.pdf")
    links = _link_line(att)
    room = AVITO_LIMIT - len(links) - 2
    text = "т" * (room + extra)

    await deliver("avito", "avito-user", text, [att], external_id=AVITO_CHAT)

    [out] = _avito_texts(rec, avito_mode)
    assert len(out) <= AVITO_LIMIT
    if extra == 0:
        assert out == f"{text}\n\n{links}", "текст впритык — без обрезки"
    else:
        assert out.endswith("…\n\n" + links), "на один знак больше — обрезка с «…»"


# --- Маскировка токена бота --------------------------------------------------


def test_mask_token_hides_bot_token():
    assert mask_token("bot123:AA-b_c") == "bot***"


def test_mask_token_inside_url_and_exception_text():
    assert mask_token("https://api.telegram.org/bot123:AA-b_c/sendMessage failed") == (
        "https://api.telegram.org/bot***/sendMessage failed"
    )
    assert mask_token(ValueError("сбой /bot5:Q_z/getMe")) == "сбой /bot***/getMe"


def test_mask_token_leaves_text_without_token_unchanged():
    text = "Telegram: chat not found (chat 100500, bot-звонок без токена)"
    assert mask_token(text) == text


# --- Сквозной POST /conversations/{id}/messages -------------------------------


@pytest.mark.asyncio
async def test_e2e_telegram_bot_pdf_with_caption(client: AsyncClient, db_session, auth_headers, net):
    conv = await _make_conv(db_session, "telegram", BOT_CHAT)
    item = await _upload_via_api(client, auth_headers, conv.id, "Договор №5.pdf")

    response = await client.post(
        f"{CONVERSATIONS_URL}/{conv.id}/messages",
        headers=auth_headers,
        json={"channel": "telegram", "content": "Договор во вложении", "attachments": [item]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["note"] is None
    assert body["message"]["delivered"] is True
    assert body["message"]["attachments"][0]["name"] == "Договор №5.pdf"
    assert _methods(net) == ["sendDocument"]
    _, fields, files = _tg(net.requests[0])
    assert fields["caption"] == "Договор во вложении"
    assert files["document"]["filename"] == "Договор №5.pdf"


@pytest.mark.asyncio
async def test_e2e_telegram_gateway_gets_public_link(
    client: AsyncClient, db_session, auth_headers, rec, net, public_base, gateway_on
):
    conv = await _make_conv(db_session, "telegram", BOT_CHAT, external_id="555")
    item = await _upload_via_api(client, auth_headers, conv.id, "Договор №5.pdf")

    response = await client.post(
        f"{CONVERSATIONS_URL}/{conv.id}/messages",
        headers=auth_headers,
        json={"channel": "telegram", "content": "Смотрите", "attachments": [item]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["note"] is None
    assert net.requests == []
    [call] = rec.enqueue
    assert call["kwargs"]["media"] == [f"{PUBLIC}{item['url']}"]


@pytest.mark.asyncio
async def test_e2e_telegram_gateway_without_public_base_returns_note(
    client: AsyncClient, db_session, auth_headers, rec, gateway_on
):
    conv = await _make_conv(db_session, "telegram", BOT_CHAT, external_id="555")
    item = await _upload_via_api(client, auth_headers, conv.id, "Договор №5.pdf")

    response = await client.post(
        f"{CONVERSATIONS_URL}/{conv.id}/messages",
        headers=auth_headers,
        json={"channel": "telegram", "content": "Смотрите", "attachments": [item]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False
    assert body["note"] == NO_PUBLIC_NOTE
    assert body["message"]["delivered"] is False
    assert rec.enqueue == []


@pytest.mark.asyncio
async def test_e2e_email_through_resend_attaches_file(
    client: AsyncClient, db_session, auth_headers, net, monkeypatch
):
    monkeypatch.setattr(mail_service, "send_email", REAL_SEND_EMAIL)

    async def settings_stub(db):
        return _resend_settings()

    monkeypatch.setattr(mail_service, "get_mail_settings", settings_stub)
    conv = await _make_conv(db_session, "email", EMAIL)
    item = await _upload_via_api(client, auth_headers, conv.id, "Договор №5.pdf")

    response = await client.post(
        f"{CONVERSATIONS_URL}/{conv.id}/messages",
        headers=auth_headers,
        json={"channel": "email", "content": "Договор во вложении", "attachments": [item]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["note"] is None
    attachment = json.loads(net.requests[0].content)["attachments"][0]
    assert attachment["filename"] == "Договор №5.pdf"
    assert base64.b64decode(attachment["content"]) == PDF


@pytest.mark.asyncio
async def test_e2e_avito_without_public_base_returns_note(
    client: AsyncClient, db_session, auth_headers, rec
):
    conv = await _make_conv(db_session, "avito", "avito-user", external_id=AVITO_CHAT)
    item = await _upload_via_api(client, auth_headers, conv.id, "Договор №5.pdf")

    response = await client.post(
        f"{CONVERSATIONS_URL}/{conv.id}/messages",
        headers=auth_headers,
        json={"channel": "avito", "content": "Договор во вложении", "attachments": [item]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False
    assert body["note"] == NO_PUBLIC_NOTE
    assert rec.send_text == []
    assert rec.enqueue == []

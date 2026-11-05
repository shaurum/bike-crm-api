"""П1: метаданные вложений при отправке.

Покрытие:
- services/attachments.py: detect_kind, normalize_content_type, safe_name,
  resolve_upload, public_url;
- POST /conversations/{id}/attachments: имя, транслитерация, 415;
- POST /conversations/{id}/messages: объекты и строки, 400 на чужой url и
  несуществующий файл.

Безопасность: _deliver подменяется записывающей заглушкой (autouse), а все
внешние точки (шлюз, Telegram, почта, Авито) дополнительно закрыты фикстурой,
которая падает при вызове. Реальной отправки клиентам тесты не делают.
"""

import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import messages as messages_api
from app.core.config import settings
from app.models import ContactPoint, Conversation, Customer, LeadMessage
from app.services.attachments import (
    detect_kind,
    normalize_content_type,
    public_url,
    resolve_upload,
    safe_name,
)

CONVERSATIONS_URL = "/api/v1/conversations"
PDF_BYTES = b"%PDF-1.4 test"
SAFE_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")


# --- Фикстуры изоляции -------------------------------------------------------


@pytest.fixture(autouse=True)
def upload_dir(tmp_path: Path, monkeypatch) -> Path:
    """uploads/ во временной папке: файлы тестов не попадают в боевой UPLOAD_DIR."""
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(root))
    return root


@pytest.fixture(autouse=True)
def deliver_calls(monkeypatch) -> List[Dict[str, Any]]:
    """Заглушка _deliver: запоминает аргументы и ничего не отправляет."""
    calls: List[Dict[str, Any]] = []

    async def fake_deliver(db, channel, recipient, content, current_user, conv, attachments=None):
        calls.append(
            {
                "channel": channel,
                "content": content,
                "attachments": attachments,
            }
        )
        return None

    monkeypatch.setattr(messages_api, "_deliver", fake_deliver)
    return calls


@pytest.fixture(autouse=True)
def no_external(monkeypatch) -> None:
    """Страховка: любой реальный вызов внешнего канала в этих тестах — ошибка."""

    def forbidden(name: str):
        async def _fail(*args, **kwargs):
            raise AssertionError(f"Внешний вызов {name} запрещён в тестах вложений")

        return _fail

    monkeypatch.setattr("app.services.gateway.enqueue_outbound", forbidden("gateway.enqueue_outbound"))
    monkeypatch.setattr("app.services.mail.send_email", forbidden("mail.send_email"))
    monkeypatch.setattr("app.services.avito.send_text", forbidden("avito.send_text"))
    monkeypatch.setattr(messages_api, "_send_telegram", forbidden("_send_telegram"))
    monkeypatch.setattr(messages_api, "_send_telegram_files", forbidden("_send_telegram_files"))


# --- Хелперы -----------------------------------------------------------------


def _write_upload(root: Path, folder: str, filename: str, data: bytes = PDF_BYTES) -> str:
    """Кладёт файл в uploads/messages/<folder>/ и возвращает его url."""
    folder_path = root / "messages" / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    (folder_path / filename).write_bytes(data)
    return f"/uploads/messages/{folder}/{filename}"


async def _make_conversation(db: AsyncSession, with_telegram: bool = True) -> Conversation:
    customer = Customer(full_name="Клиент вложений")
    db.add(customer)
    await db.flush()
    if with_telegram:
        db.add(
            ContactPoint(
                customer_id=customer.id,
                channel="telegram",
                value="@client_att",
                is_primary=True,
            )
        )
    conversation = Conversation(customer_id=customer.id, status="open")
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


def _messages_url(conversation_id) -> str:
    return f"{CONVERSATIONS_URL}/{conversation_id}/messages"


async def _saved_messages(db: AsyncSession, conversation_id) -> List[LeadMessage]:
    result = await db.execute(
        select(LeadMessage)
        .where(LeadMessage.conversation_id == conversation_id)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


# --- detect_kind -------------------------------------------------------------

DETECT_KIND_CASES = [
    # изображения
    ("photo.jpg", "image/jpeg", "image"),
    ("photo.jpeg", None, "image"),
    ("photo.png", "image/png", "image"),
    ("photo.webp", "image/webp", "image"),
    ("PHOTO.JPG", "image/jpeg", "image"),
    # анимация
    ("anim.gif", "image/gif", "animation"),
    # HEIC — документ, Telegram его не показывает как фото
    ("photo.heic", "image/heic", "document"),
    ("photo.heic", None, "document"),
    # голосовые
    ("voice.ogg", "audio/ogg", "voice"),
    ("voice.oga", "application/octet-stream", "voice"),
    ("voice.opus", None, "voice"),
    # аудио
    ("song.mp3", "audio/mpeg", "audio"),
    ("rec.m4a", "audio/mp4", "audio"),
    # видео
    ("clip.mp4", "video/mp4", "video"),
    ("clip.mov", "video/quicktime", "video"),
    ("clip.webm", "video/webm", "video"),
    # документы
    ("Договор.pdf", "application/pdf", "document"),
    (
        "Договор.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "document",
    ),
    ("Договор.pdf", None, "document"),
    # приоритет расширения над content-type
    ("voice.ogg", "audio/mpeg", "voice"),
    ("photo.heic", "image/jpeg", "document"),
    # вид по content-type, когда расширения нет
    ("file", "image/jpeg", "image"),
    ("file", "Image/PNG; q=1", "image"),
    ("file", "image/gif", "animation"),
    ("file", "image/heic", "document"),
    ("file", "audio/mpeg", "audio"),
    ("file", "audio/ogg", "audio"),
    ("file", "video/mp4", "video"),
    ("file", "application/pdf", "document"),
    ("file", "application/octet-stream", "document"),
    ("file", None, "document"),
]


@pytest.mark.parametrize("name, content_type, expected", DETECT_KIND_CASES)
def test_detect_kind(name, content_type, expected):
    assert detect_kind(name, content_type) == expected


# --- normalize_content_type --------------------------------------------------

NORMALIZE_CASES = [
    # пустой/octet-stream у .oga/.opus/.ogg -> audio/ogg
    ("voice.oga", "application/octet-stream", "audio/ogg"),
    ("voice.ogg", "", "audio/ogg"),
    ("voice.opus", None, "audio/ogg"),
    ("Voice.OGG", "application/octet-stream", "audio/ogg"),
    # пустой/octet-stream у прочих -> по расширению
    ("Договор.pdf", "", "application/pdf"),
    ("Договор.pdf", None, "application/pdf"),
    ("Договор.pdf", "application/octet-stream", "application/pdf"),
    # явный тип сохраняется как есть (параметры отбрасываются)
    ("Договор.pdf", "application/pdf", "application/pdf"),
    ("a.pdf", "text/plain", "text/plain"),
    ("a.jpg", "image/png", "image/png"),
    ("a.pdf", "application/pdf; charset=binary", "application/pdf"),
    # ничего не знаем
    ("noext", "", "application/octet-stream"),
]


@pytest.mark.parametrize("name, content_type, expected", NORMALIZE_CASES)
def test_normalize_content_type(name, content_type, expected):
    assert normalize_content_type(name, content_type) == expected


# --- safe_name ---------------------------------------------------------------


def test_safe_name_transliterates_cyrillic():
    assert safe_name("Счёт март.pdf", ".pdf") == "Schet_mart.pdf"


def test_safe_name_transliterates_number_sign():
    assert safe_name("Договор №5.pdf", ".pdf") == "Dogovor_5.pdf"


@pytest.mark.parametrize("original", ["???.pdf", "", "   .pdf"])
def test_safe_name_falls_back_to_file(original):
    assert safe_name(original, ".pdf") == "file.pdf"


def test_safe_name_drops_directories():
    assert safe_name("../../etc/passwd.pdf", ".pdf") == "passwd.pdf"


def test_safe_name_long_name_is_capped():
    result = safe_name("а" * 200 + ".pdf", ".pdf")
    assert len(result) <= 80
    assert result.endswith(".pdf")
    assert result == "a" * 76 + ".pdf"


@pytest.mark.parametrize("original", ["Счёт март.pdf", "Договор №5.pdf", "я ё ъ.docx", "???.pdf"])
def test_safe_name_only_latin_allowed(original):
    ext = os.path.splitext(original)[1] or ".bin"
    result = safe_name(original, ext)
    stem, got_ext = os.path.splitext(result)
    assert got_ext == ext
    assert SAFE_NAME_RE.fullmatch(result), result


# --- resolve_upload ----------------------------------------------------------


@pytest.fixture
def layout(tmp_path: Path, upload_dir: Path) -> Dict[str, Path]:
    """Файлы внутри uploads/ и «секрет» снаружи, плюс соседняя папка-обманка."""
    inside = upload_dir / "messages" / "att-1" / "Schet_mart.pdf"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(PDF_BYTES)

    other = upload_dir / "other" / "x.pdf"
    other.parent.mkdir(parents=True)
    other.write_bytes(PDF_BYTES)

    secret = tmp_path / "secret.txt"
    secret.write_text("secret")

    sibling = tmp_path / "uploads_evil" / "x.pdf"
    sibling.parent.mkdir(parents=True)
    sibling.write_bytes(PDF_BYTES)

    return {"inside": inside, "other": other, "secret": secret, "sibling": sibling}


def test_resolve_upload_returns_existing_file(layout):
    assert resolve_upload("/uploads/messages/att-1/Schet_mart.pdf") == os.path.abspath(
        str(layout["inside"])
    )


@pytest.mark.parametrize(
    "url",
    [
        "/uploads/../secret.txt",
        "/uploads/messages/../../secret.txt",
        "/uploads/../../secret.txt",
        "/uploads/../uploads_evil/x.pdf",
    ],
)
def test_resolve_upload_blocks_traversal(layout, url):
    assert resolve_upload(url) is None


def test_resolve_upload_subdir_restricts_to_folder(layout):
    assert resolve_upload("/uploads/other/x.pdf") is not None
    assert resolve_upload("/uploads/other/x.pdf", "messages") is None
    assert resolve_upload("/uploads/messages/att-1/Schet_mart.pdf", "messages") is not None


def test_resolve_upload_subdir_blocks_traversal_out_of_folder(layout):
    assert resolve_upload("/uploads/messages/../other/x.pdf", "messages") is None


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/a.pdf",
        "/etc/passwd",
        "messages/att-1/Schet_mart.pdf",
        "/uploads/messages/att-1/none.pdf",
        "/uploads/messages/att-1",
    ],
)
def test_resolve_upload_rejects_non_files(layout, url):
    assert resolve_upload(url) is None


# --- public_url --------------------------------------------------------------


def test_public_url_without_base_is_none(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "")
    assert public_url("/uploads/messages/att-1/Schet_mart.pdf") is None


def test_public_url_builds_full_link(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://crm.example.ru/")
    assert (
        public_url("/uploads/messages/att-1/Schet_mart.pdf")
        == "https://crm.example.ru/uploads/messages/att-1/Schet_mart.pdf"
    )


def test_public_url_strips_trailing_slash_only_once(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://crm.example.ru")
    assert (
        public_url("/uploads/messages/att-1/Schet_mart.pdf")
        == "https://crm.example.ru/uploads/messages/att-1/Schet_mart.pdf"
    )


def test_public_url_quotes_path_parts(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://crm.example.ru")
    url = public_url("/uploads/messages/att-1/Договор №5.pdf")
    assert url == "https://crm.example.ru/uploads/messages/att-1/" + quote("Договор №5.pdf", safe="")
    assert " " not in url


@pytest.mark.parametrize("base", ["", "https://crm.example.ru"])
def test_public_url_returns_external_links_as_is(monkeypatch, base):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", base)
    assert public_url("https://cdn.example.com/a.pdf") == "https://cdn.example.com/a.pdf"
    assert public_url("http://cdn.example.com/a.pdf") == "http://cdn.example.com/a.pdf"


def test_public_url_ignores_non_upload_paths(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://crm.example.ru")
    assert public_url("/api/v1/conversations") is None


# --- POST /conversations/{id}/attachments ------------------------------------


@pytest.mark.asyncio
async def test_upload_cyrillic_pdf_gets_latin_path(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir: Path
):
    conv = await _make_conversation(db_session, with_telegram=False)

    response = await client.post(
        f"{CONVERSATIONS_URL}/{conv.id}/attachments",
        headers=auth_headers,
        files={"file": ("Счёт март.pdf", PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert re.fullmatch(
        r"/uploads/messages/att-[0-9a-f]{32}/Schet_mart\.pdf", body["url"]
    ), body["url"]
    assert body["name"] == "Счёт март.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["size"] == len(PDF_BYTES)

    folder = body["url"].split("/")[3]
    saved = upload_dir / "messages" / folder / "Schet_mart.pdf"
    assert saved.is_file()
    assert saved.read_bytes() == PDF_BYTES


@pytest.mark.asyncio
async def test_upload_unsupported_ext_is_415(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir: Path
):
    conv = await _make_conversation(db_session, with_telegram=False)

    response = await client.post(
        f"{CONVERSATIONS_URL}/{conv.id}/attachments",
        headers=auth_headers,
        files={"file": ("virus.exe", b"MZ\x00\x00", "application/octet-stream")},
    )

    assert response.status_code == 415, response.text
    assert not (upload_dir / "messages").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", ["application/pdf", "image/png"])
async def test_upload_exe_with_spoofed_content_type_is_415(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir: Path, content_type
):
    """Расширение .exe явно запрещено; подменённый Content-Type не должен его обойти.

    Сейчас upload_attachment при неразрешённом расширении берёт ext из
    mimetypes.guess_extension(content_type) — см. messages.py, upload_attachment.
    """
    conv = await _make_conversation(db_session, with_telegram=False)

    response = await client.post(
        f"{CONVERSATIONS_URL}/{conv.id}/attachments",
        headers=auth_headers,
        files={"file": ("virus.exe", b"MZ\x00\x00", content_type)},
    )

    assert response.status_code == 415, response.text
    assert not (upload_dir / "messages").exists()


# --- POST /conversations/{id}/messages ---------------------------------------


@pytest.mark.asyncio
async def test_send_object_attachment_keeps_all_fields(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir: Path, deliver_calls
):
    conv = await _make_conversation(db_session)
    url = _write_upload(upload_dir, f"att-{uuid.uuid4().hex}", "Schet_mart.pdf")
    expected = {
        "url": url,
        "name": "Договор №5.pdf",
        "content_type": "application/pdf",
        "size": 2048,
    }

    response = await client.post(
        _messages_url(conv.id),
        headers=auth_headers,
        json={"channel": "telegram", "content": "Договор во вложении", "attachments": [expected]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["message"]["attachments"] == [expected]

    saved = await _saved_messages(db_session, conv.id)
    assert len(saved) == 1
    assert saved[0].attachments == [expected]

    assert len(deliver_calls) == 1
    assert deliver_calls[0]["attachments"] == [expected]
    assert set(deliver_calls[0]["attachments"][0]) == {"url", "name", "content_type", "size"}


@pytest.mark.asyncio
async def test_send_string_attachment_still_works(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir: Path, deliver_calls
):
    conv = await _make_conversation(db_session)
    url = _write_upload(upload_dir, f"att-{uuid.uuid4().hex}", "Schet_mart.pdf", b"x" * 100)

    response = await client.post(
        _messages_url(conv.id),
        headers=auth_headers,
        json={"channel": "telegram", "content": "", "attachments": [url]},
    )

    assert response.status_code == 200, response.text
    expected = {
        "url": url,
        "name": "Schet_mart.pdf",
        "content_type": "application/pdf",
        "size": 100,
    }
    assert response.json()["message"]["attachments"] == [expected]
    saved = await _saved_messages(db_session, conv.id)
    assert saved[0].attachments == [expected]
    assert deliver_calls[0]["attachments"] == [expected]


@pytest.mark.asyncio
async def test_send_object_without_meta_fills_from_file(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir: Path
):
    conv = await _make_conversation(db_session)
    url = _write_upload(upload_dir, f"att-{uuid.uuid4().hex}", "Schet_mart.pdf", b"y" * 321)

    response = await client.post(
        _messages_url(conv.id),
        headers=auth_headers,
        json={"channel": "telegram", "content": "x", "attachments": [{"url": url}]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["message"]["attachments"] == [
        {"url": url, "name": "Schet_mart.pdf", "content_type": "application/pdf", "size": 321}
    ]


@pytest.mark.asyncio
async def test_upload_then_send_roundtrip(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir: Path, deliver_calls
):
    """Ответ загрузки подставляется в отправку как есть (контракт фронтенда)."""
    conv = await _make_conversation(db_session)

    uploaded = await client.post(
        f"{CONVERSATIONS_URL}/{conv.id}/attachments",
        headers=auth_headers,
        files={"file": ("Счёт март.pdf", PDF_BYTES, "application/pdf")},
    )
    assert uploaded.status_code == 200, uploaded.text
    item = uploaded.json()

    sent = await client.post(
        _messages_url(conv.id),
        headers=auth_headers,
        json={"channel": "telegram", "content": "", "attachments": [item]},
    )

    assert sent.status_code == 200, sent.text
    assert sent.json()["message"]["attachments"] == [item]
    assert deliver_calls[0]["attachments"] == [item]


REJECTED_URLS = [
    pytest.param("https://example.com/a.pdf", id="external_url"),
    pytest.param("/uploads/other/x.pdf", id="outside_messages_folder"),
    pytest.param("/uploads/messages/../other/x.pdf", id="traversal_into_other_folder"),
    pytest.param("/uploads/messages/../../secret.txt", id="traversal_outside_uploads"),
    pytest.param("/uploads/messages/att-nope/none.pdf", id="missing_file"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("url", REJECTED_URLS)
async def test_send_rejects_bad_attachment_url(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers,
    upload_dir: Path,
    deliver_calls,
    url: str,
):
    conv = await _make_conversation(db_session)
    # Файлы, на которые ссылаются плохие url, существуют (кроме missing_file):
    # отказ должен идти из-за префикса/пути, а не из-за отсутствия файла.
    (upload_dir / "other").mkdir(exist_ok=True)
    (upload_dir / "other" / "x.pdf").write_bytes(PDF_BYTES)
    (upload_dir.parent / "secret.txt").write_text("secret")

    response = await client.post(
        _messages_url(conv.id),
        headers=auth_headers,
        json={
            "channel": "telegram",
            "content": "тест",
            "attachments": [{"url": url, "name": "x.pdf"}],
        },
    )

    assert response.status_code == 400, response.text
    assert "Вложение не найдено" in response.json()["detail"]
    assert deliver_calls == []
    assert await _saved_messages(db_session, conv.id) == []


@pytest.mark.asyncio
async def test_send_with_one_bad_attachment_saves_nothing(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir: Path, deliver_calls
):
    conv = await _make_conversation(db_session)
    good = _write_upload(upload_dir, f"att-{uuid.uuid4().hex}", "Schet_mart.pdf")

    response = await client.post(
        _messages_url(conv.id),
        headers=auth_headers,
        json={
            "channel": "telegram",
            "content": "тест",
            "attachments": [good, "/uploads/messages/att-nope/none.pdf"],
        },
    )

    assert response.status_code == 400, response.text
    assert deliver_calls == []
    assert await _saved_messages(db_session, conv.id) == []

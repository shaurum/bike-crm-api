"""П4 (backend): входящие медиа Telegram — типы и имена файлов.

Покрытие:
- services/tg_media.py: save_tg_file (voice / document / pdf, ошибки getFile и скачивания),
  extract_attachments (вложения из photo + voice);
- tasks/sync_gateway.py: _resolve_attachments передаёт kind в save_tg_file.

Безопасность: все HTTP-вызовы к api.telegram.org идут через httpx.MockTransport.
Запросы к любому другому хосту получают 404 и записываются в журнал, реальной сети нет.
save_tg_file глотает исключения (возвращает None), поэтому проверки ошибок опираются
на журнал запросов и отсутствие файлов на диске, а не на исключения.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Tuple

import httpx
import pytest

from app.core.config import settings
from app.services import tg_media
from app.tasks import sync_gateway, webhooks

TOKEN = "111222TESTTOKEN"
TG_HOST = "api.telegram.org"
OGG_BYTES = b"OggS\x00\x02fake-opus-payload"
JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg"
PDF_BYTES = b"%PDF-1.4 fake"

# Настоящий класс сохраняем до подмены: фабрика ниже создаёт клиент через него.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


class TgServer:
    """Фейковый api.telegram.org: getFile и скачивание файла по file_path.

    files: file_id -> (file_path, содержимое, content-type заголовка или None).
    """

    def __init__(self) -> None:
        self.files: Dict[str, Tuple[str, bytes, object]] = {}
        self.requests: List[str] = []
        self.fail_get_file: set = set()
        self.fail_download: set = set()
        self.raise_on_download: set = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        if request.url.host != TG_HOST:
            return httpx.Response(404, text="unexpected host")

        if request.url.path == f"/bot{TOKEN}/getFile":
            file_id = request.url.params.get("file_id", "")
            if file_id in self.fail_get_file or file_id not in self.files:
                return httpx.Response(400, json={"ok": False, "description": "Bad Request"})
            file_path = self.files[file_id][0]
            return httpx.Response(
                200,
                json={"ok": True, "result": {"file_id": file_id, "file_path": file_path}},
            )

        prefix = f"/file/bot{TOKEN}/"
        if request.url.path.startswith(prefix):
            wanted = request.url.path[len(prefix):]
            for file_id, (file_path, content, ctype) in self.files.items():
                if file_path != wanted:
                    continue
                if file_id in self.raise_on_download:
                    raise httpx.ConnectError("сеть недоступна (тест)", request=request)
                if file_id in self.fail_download:
                    return httpx.Response(500, text="server error")
                headers = {} if ctype is None else {"content-type": ctype}
                return httpx.Response(200, content=content, headers=headers)

        return httpx.Response(404, text="unknown url")


def _client(server: TgServer) -> httpx.AsyncClient:
    return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(server.handler), follow_redirects=True)


def _saved_files(upload_root: Path) -> List[Path]:
    target = upload_root / "messages"
    return sorted(target.iterdir()) if target.exists() else []


def _assert_only_telegram(server: TgServer) -> None:
    assert server.requests, "ожидались запросы к фейковому Telegram"
    assert all(url.startswith(f"https://{TG_HOST}/") for url in server.requests), server.requests


# --- Фикстуры изоляции -------------------------------------------------------


@pytest.fixture
def upload_root(tmp_path: Path, monkeypatch) -> Path:
    """UPLOAD_DIR во временной папке: файлы тестов не попадают в боевой uploads."""
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(root))
    return root


@pytest.fixture
def tg(monkeypatch, upload_root: Path) -> TgServer:
    """Фейковый Telegram и подмена httpx.AsyncClient внутри модуля tg_media.

    extract_attachments создаёт клиент сам: фабрика подставляет MockTransport.
    Подмена касается только имени httpx внутри tg_media, глобальный httpx не меняется.
    """
    server = TgServer()

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return _REAL_ASYNC_CLIENT(*args, transport=httpx.MockTransport(server.handler), **kwargs)

    monkeypatch.setattr(tg_media, "httpx", SimpleNamespace(AsyncClient=factory))
    return server


# --- save_tg_file: типы и имена ----------------------------------------------


@pytest.mark.parametrize(
    "ctype",
    ["application/octet-stream", ""],
    ids=["octet-stream", "empty-header"],
)
async def test_voice_octet_stream_saved_as_ogg(tg: TgServer, upload_root: Path, ctype: str):
    tg.files = {"VOICE1": ("voice/file_1.oga", OGG_BYTES, ctype)}

    async with _client(tg) as client:
        saved = await tg_media.save_tg_file(TOKEN, "VOICE1", kind="voice", client=client)

    assert saved is not None
    assert saved["name"] == "Голосовое.ogg"
    assert saved["content_type"] == "audio/ogg"
    assert saved["url"].startswith("/uploads/messages/tg-")
    assert saved["url"].endswith(".ogg")

    on_disk = upload_root / "messages" / Path(saved["url"]).name
    assert on_disk.suffix == ".ogg"
    assert on_disk.is_file()
    assert on_disk.read_bytes() == OGG_BYTES
    assert _saved_files(upload_root) == [on_disk]
    _assert_only_telegram(tg)


async def test_voice_with_explicit_name_keeps_name(tg: TgServer, upload_root: Path):
    tg.files = {"VOICE2": ("voice/file_2.oga", OGG_BYTES, "application/octet-stream")}

    async with _client(tg) as client:
        saved = await tg_media.save_tg_file(
            TOKEN, "VOICE2", name="Запись клиента.ogg", kind="voice", client=client
        )

    assert saved is not None
    assert saved["name"] == "Запись клиента.ogg"
    assert saved["content_type"] == "audio/ogg"
    assert saved["url"].endswith(".ogg")
    assert (upload_root / "messages" / Path(saved["url"]).name).read_bytes() == OGG_BYTES


async def test_document_jpg_octet_stream_is_image_jpeg(tg: TgServer, upload_root: Path):
    tg.files = {"DOC1": ("documents/file_3.jpg", JPEG_BYTES, "application/octet-stream")}

    async with _client(tg) as client:
        saved = await tg_media.save_tg_file(
            TOKEN, "DOC1", name="photo.jpg", kind="document", client=client
        )

    assert saved is not None
    assert saved["name"] == "photo.jpg"
    assert saved["content_type"] == "image/jpeg"
    assert saved["url"].endswith(".jpg")
    assert (upload_root / "messages" / Path(saved["url"]).name).read_bytes() == JPEG_BYTES


async def test_pdf_explicit_type_is_kept(tg: TgServer, upload_root: Path):
    tg.files = {"PDF1": ("documents/file_7.pdf", PDF_BYTES, "application/pdf")}

    async with _client(tg) as client:
        saved = await tg_media.save_tg_file(
            TOKEN, "PDF1", name="Договор №5.pdf", kind="document", client=client
        )

    assert saved is not None
    assert saved["name"] == "Договор №5.pdf"
    assert saved["content_type"] == "application/pdf"
    assert saved["url"].endswith(".pdf")


# --- save_tg_file: ошибки ----------------------------------------------------


@pytest.mark.parametrize(
    "scenario",
    ["get_file_http_error", "get_file_no_file_path", "download_http_error", "download_connect_error"],
)
async def test_download_errors_return_none(tg: TgServer, upload_root: Path, scenario: str):
    tg.files = {"BAD": ("voice/file_9.oga", OGG_BYTES, "application/octet-stream")}
    if scenario == "get_file_http_error":
        tg.fail_get_file.add("BAD")
    elif scenario == "get_file_no_file_path":
        tg.files["BAD"] = ("", OGG_BYTES, "application/octet-stream")
    elif scenario == "download_http_error":
        tg.fail_download.add("BAD")
    elif scenario == "download_connect_error":
        tg.raise_on_download.add("BAD")

    async with _client(tg) as client:
        saved = await tg_media.save_tg_file(TOKEN, "BAD", kind="voice", client=client)

    assert saved is None
    assert _saved_files(upload_root) == [], "при ошибке файл на диск не должен попадать"
    _assert_only_telegram(tg)


# --- extract_attachments -----------------------------------------------------


async def test_extract_attachments_photo_and_voice(tg: TgServer, upload_root: Path):
    tg.files = {
        "PHOTO_SMALL": ("photos/file_0.jpg", b"small", "image/jpeg"),
        "PHOTO_BIG": ("photos/file_1.jpg", JPEG_BYTES, "image/jpeg"),
        "VOICE1": ("voice/file_2.oga", OGG_BYTES, "application/octet-stream"),
    }
    message = {
        "message_id": 10,
        "photo": [
            {"file_id": "PHOTO_SMALL", "width": 90, "height": 90},
            {"file_id": "PHOTO_BIG", "width": 1280, "height": 960},
        ],
        "voice": {"file_id": "VOICE1", "duration": 3},
    }

    result = await tg_media.extract_attachments(TOKEN, message)

    assert len(result) == 2
    photo, voice = result
    assert photo["content_type"] == "image/jpeg"
    assert photo["name"] == "file_1.jpg"
    assert voice["name"] == "Голосовое.ogg"
    assert voice["content_type"] == "audio/ogg"

    # для фото берётся самое крупное разрешение
    assert any("file_id=PHOTO_BIG" in url for url in tg.requests)
    assert not any("file_id=PHOTO_SMALL" in url for url in tg.requests)

    messages_dir = upload_root / "messages"
    assert (messages_dir / Path(photo["url"]).name).read_bytes() == JPEG_BYTES
    assert (messages_dir / Path(voice["url"]).name).read_bytes() == OGG_BYTES
    _assert_only_telegram(tg)


async def test_extract_attachments_failed_file_does_not_drop_others(tg: TgServer, upload_root: Path):
    tg.files = {
        "PHOTO1": ("photos/file_1.jpg", JPEG_BYTES, "image/jpeg"),
        "VOICE1": ("voice/file_2.oga", OGG_BYTES, "application/octet-stream"),
    }
    tg.fail_get_file.add("VOICE1")
    message = {
        "photo": [{"file_id": "PHOTO1"}],
        "voice": {"file_id": "VOICE1"},
    }

    result = await tg_media.extract_attachments(TOKEN, message)

    assert [item["content_type"] for item in result] == ["image/jpeg"]


async def test_extract_attachments_without_media_makes_no_requests(tg: TgServer, upload_root: Path):
    result = await tg_media.extract_attachments(TOKEN, {"message_id": 1, "text": "привет"})

    assert result == []
    assert tg.requests == []


# --- sync_gateway._resolve_attachments ---------------------------------------


@pytest.fixture
def saved_calls(monkeypatch) -> List[dict]:
    """Подмена save_tg_file: запоминает аргументы. _resolve_attachments импортирует её при вызове."""
    calls: List[dict] = []

    async def fake_save(token, file_id, *, name=None, kind=None, client=None):
        calls.append({"token": token, "file_id": file_id, "name": name, "kind": kind, "client": client})
        return {"url": f"/uploads/messages/fake-{file_id}", "name": name or file_id, "content_type": "x/y"}

    monkeypatch.setattr(tg_media, "save_tg_file", fake_save)
    return calls


@pytest.fixture
def token_from_db(monkeypatch) -> dict:
    """Подмена _telegram_token: в тестах не ходим в БД за токеном бота."""
    state = {"token": TOKEN}

    async def fake_token(session):
        return state["token"]

    monkeypatch.setattr(webhooks, "_telegram_token", fake_token)
    return state


async def test_resolve_attachments_passes_kind(saved_calls: List[dict], token_from_db: dict):
    raw = [
        {"file_id": "VOICE1", "kind": "voice"},
        {"file_id": "DOC1", "kind": "document", "name": "Договор.pdf"},
        {"file_id": "PHOTO1", "kind": "photo"},
        {"url": "/uploads/messages/already.pdf", "name": "already.pdf", "content_type": "application/pdf"},
    ]

    out = await sync_gateway._resolve_attachments(None, raw)

    assert [(c["file_id"], c["kind"], c["name"]) for c in saved_calls] == [
        ("VOICE1", "voice", None),
        ("DOC1", "document", "Договор.pdf"),
        ("PHOTO1", "photo", None),
    ]
    assert all(c["token"] == TOKEN for c in saved_calls)
    # элемент с готовым url не скачивается, но попадает в результат
    assert len(out) == 4
    assert out[-1]["url"] == "/uploads/messages/already.pdf"


async def test_resolve_attachments_json_string_input(saved_calls: List[dict], token_from_db: dict):
    raw = '[{"file_id": "VOICE9", "kind": "voice"}]'

    out = await sync_gateway._resolve_attachments(None, raw)

    assert [(c["file_id"], c["kind"]) for c in saved_calls] == [("VOICE9", "voice")]
    assert len(out) == 1


async def test_resolve_attachments_without_token_skips_download(
    saved_calls: List[dict], token_from_db: dict
):
    token_from_db["token"] = None
    raw = [{"file_id": "VOICE1", "kind": "voice"}]

    out = await sync_gateway._resolve_attachments(None, raw)

    assert saved_calls == []
    assert out == []

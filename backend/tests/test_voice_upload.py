"""П5: загрузка голосовых (voice=1) и обычных вложений без перекодирования.

Покрытие POST /conversations/{id}/attachments:
1. webm/opus + voice=1 -> OGG/Opus, имя «Голосовое.ogg», audio/ogg;
2. m4a/aac (audio/mp4) + voice=1 -> перекодируется в OGG/Opus;
3. ogg + voice=1 -> байты не меняются (ffmpeg не вызывается);
4. мусор под видом .webm + voice=1 -> 422, файла нет;
5. ffmpeg отсутствует (FileNotFoundError) -> 422;
6. ffmpeg «висит», таймаут мал -> 422, процесс убит;
7. без voice webm сохраняется как есть (П1), ffmpeg не вызывается;
8. файл больше MAX_UPLOAD_MB с voice=1 -> 413, ffmpeg не вызывается.

Безопасность: тесты только загружают файлы во временный uploads/. Ни шлюз,
ни Telegram, ни почта, ни Авито в них не вызываются. Входные медиа генерирует
сам ffmpeg внутри контейнера (-f lavfi -i sine=d=1).
"""

import asyncio
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import messages as messages_api
from app.core.config import settings
from app.models import Conversation, Customer

CONVERSATIONS_URL = "/api/v1/conversations"
VOICE_NAME = "Голосовое.ogg"
VOICE_ERROR = "Не удалось обработать запись"
VOICE_URL_RE = re.compile(r"/uploads/messages/att-[0-9a-f]{32}/voice\.ogg")


# --- Фикстуры ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def upload_dir(tmp_path: Path, monkeypatch) -> Path:
    """uploads/ во временной папке: боевой UPLOAD_DIR (/app/uploads) не трогаем."""
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(root))
    return root


@pytest.fixture(scope="module")
def media(tmp_path_factory) -> Dict[str, bytes]:
    """Входные файлы, сгенерированные ffmpeg-ом в контейнере."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.fail("ffmpeg/ffprobe не найдены в контейнере api: образ собран без них")

    folder = tmp_path_factory.mktemp("voice_src")
    recipes = {
        "webm": ["-c:a", "libopus"],
        "m4a": ["-c:a", "aac"],
        "ogg": ["-c:a", "libopus"],
    }
    out: Dict[str, bytes] = {}
    for ext, codec_args in recipes.items():
        path = folder / f"src.{ext}"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "sine=d=1",
                *codec_args,
                str(path),
            ],
            check=True,
            timeout=60,
        )
        out[ext] = path.read_bytes()
    return out


@pytest.fixture
def ffmpeg_spy(monkeypatch) -> List[tuple]:
    """Записывает все вызовы asyncio.create_subprocess_exec и пропускает их дальше."""
    calls: List[tuple] = []
    real_exec = asyncio.create_subprocess_exec

    async def spy(*args, **kwargs):
        calls.append(args)
        return await real_exec(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    return calls


# --- Хелперы -----------------------------------------------------------------


async def _make_conversation(db: AsyncSession) -> Conversation:
    customer = Customer(full_name="Клиент голосовых")
    db.add(customer)
    await db.flush()
    conversation = Conversation(customer_id=customer.id, status="open")
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def _upload(
    client: AsyncClient,
    headers: Dict[str, str],
    conversation_id,
    filename: str,
    data: bytes,
    content_type: str,
    voice: bool = False,
):
    form = {"voice": "1"} if voice else {}
    return await client.post(
        f"{CONVERSATIONS_URL}/{conversation_id}/attachments",
        headers=headers,
        files={"file": (filename, data, content_type)},
        data=form,
    )


def _saved_path(upload_dir: Path, url: str) -> Path:
    """/uploads/messages/att-x/voice.ogg -> <upload_dir>/messages/att-x/voice.ogg."""
    assert url.startswith("/uploads/"), url
    return upload_dir / url.removeprefix("/uploads/")


def _probe(path: Path):
    """(codec_name, channels, format_name) первого аудиопотока через ffprobe."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,channels",
            "-show_entries", "format=format_name",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    data = json.loads(out.stdout)
    stream = data["streams"][0]
    return stream["codec_name"], int(stream["channels"]), data["format"]["format_name"]


def _saved_files(upload_dir: Path) -> List[Path]:
    return [p for p in upload_dir.rglob("*") if p.is_file()]


# --- 1. webm/opus + voice=1 --------------------------------------------------


@pytest.mark.asyncio
async def test_webm_opus_voice_is_transcoded_to_ogg_opus(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir, media, ffmpeg_spy
):
    conv = await _make_conversation(db_session)

    response = await _upload(
        client, auth_headers, conv.id, "Запись.webm", media["webm"], "audio/webm;codecs=opus", voice=True
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert VOICE_URL_RE.fullmatch(body["url"]), body["url"]
    assert body["name"] == VOICE_NAME
    assert body["content_type"] == "audio/ogg"
    assert len(ffmpeg_spy) == 1, "webm должен перекодироваться ffmpeg-ом"

    saved = _saved_path(upload_dir, body["url"])
    assert saved.is_file()
    assert body["size"] == saved.stat().st_size

    codec, channels, fmt = _probe(saved)
    assert codec == "opus"
    assert fmt == "ogg"
    assert channels == 1


# --- 2. m4a/aac + voice=1 ----------------------------------------------------


@pytest.mark.asyncio
async def test_m4a_aac_voice_is_transcoded_to_ogg_opus(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir, media, ffmpeg_spy
):
    conv = await _make_conversation(db_session)

    response = await _upload(
        client, auth_headers, conv.id, "Запись.m4a", media["m4a"], "audio/mp4", voice=True
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert VOICE_URL_RE.fullmatch(body["url"]), body["url"]
    assert body["name"] == VOICE_NAME
    assert body["content_type"] == "audio/ogg"
    assert len(ffmpeg_spy) == 1, "m4a должен перекодироваться ffmpeg-ом"

    saved = _saved_path(upload_dir, body["url"])
    assert saved.read_bytes() != media["m4a"]

    codec, channels, fmt = _probe(saved)
    assert codec == "opus"
    assert fmt == "ogg"
    assert channels == 1


# --- 3. ogg + voice=1: без перекодирования ------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["Запись.ogg", "Запись.oga", "Запись.opus"])
async def test_ogg_voice_is_saved_byte_for_byte(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir, media, ffmpeg_spy, filename
):
    conv = await _make_conversation(db_session)

    response = await _upload(
        client, auth_headers, conv.id, filename, media["ogg"], "audio/ogg", voice=True
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert VOICE_URL_RE.fullmatch(body["url"]), body["url"]
    assert body["name"] == VOICE_NAME
    assert body["content_type"] == "audio/ogg"
    assert ffmpeg_spy == [], "ogg/oga/opus не должны перекодироваться"

    saved = _saved_path(upload_dir, body["url"])
    assert saved.read_bytes() == media["ogg"]


# --- 4. мусор под видом webm + voice=1 ---------------------------------------


@pytest.mark.asyncio
async def test_garbage_as_webm_voice_is_422_and_nothing_saved(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir, ffmpeg_spy
):
    conv = await _make_conversation(db_session)
    garbage = b"this is definitely not a media file\x00\x01\x02" * 200

    response = await _upload(
        client, auth_headers, conv.id, "fake.webm", garbage, "audio/webm", voice=True
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == VOICE_ERROR
    assert len(ffmpeg_spy) == 1, "ошибка должна прийти из ffmpeg, а не из проверок до него"
    assert _saved_files(upload_dir) == []


# --- 5. ffmpeg отсутствует ----------------------------------------------------


@pytest.mark.asyncio
async def test_missing_ffmpeg_is_422(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir, media, monkeypatch
):
    conv = await _make_conversation(db_session)

    async def no_ffmpeg(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "ffmpeg")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", no_ffmpeg)

    response = await _upload(
        client, auth_headers, conv.id, "Запись.webm", media["webm"], "audio/webm", voice=True
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == VOICE_ERROR
    assert _saved_files(upload_dir) == []


# --- 6. таймаут ffmpeg --------------------------------------------------------


class _HangingProcess:
    """Имитация зависшего ffmpeg: wait() не возвращается, пока не вызван kill()."""

    def __init__(self) -> None:
        self.returncode = None
        self.killed = False
        self._done: asyncio.Event | None = None

    def _event(self) -> asyncio.Event:
        if self._done is None:
            self._done = asyncio.Event()
        return self._done

    async def wait(self) -> int:
        await self._event().wait()
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self._event().set()


@pytest.mark.asyncio
async def test_ffmpeg_timeout_is_422_and_process_is_killed(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir, media, monkeypatch
):
    conv = await _make_conversation(db_session)
    proc = _HangingProcess()

    async def hanging_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", hanging_exec)
    # VOICE_FFMPEG_TIMEOUT — модульная константа, читается при вызове: подменяем её.
    monkeypatch.setattr(messages_api, "VOICE_FFMPEG_TIMEOUT", 0.2)

    # Страховка от зависания самого теста, если таймаут не сработает
    response = await asyncio.wait_for(
        _upload(client, auth_headers, conv.id, "Запись.webm", media["webm"], "audio/webm", voice=True),
        timeout=15,
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == VOICE_ERROR
    assert proc.killed is True
    assert _saved_files(upload_dir) == []


# --- 7. без voice: webm как есть (П1) ----------------------------------------


@pytest.mark.asyncio
async def test_webm_without_voice_is_saved_as_is(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir, media, ffmpeg_spy
):
    conv = await _make_conversation(db_session)

    response = await _upload(
        client, auth_headers, conv.id, "Запись.webm", media["webm"], "audio/webm;codecs=opus"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert not body["url"].endswith("/voice.ogg")
    assert re.fullmatch(r"/uploads/messages/att-[0-9a-f]{32}/[A-Za-z0-9._-]+\.webm", body["url"]), body["url"]
    assert body["name"] == "Запись.webm"
    assert body["content_type"] == "audio/webm"
    assert ffmpeg_spy == [], "без voice перекодирования быть не должно"

    saved = _saved_path(upload_dir, body["url"])
    assert saved.read_bytes() == media["webm"]


# --- 8. больше MAX_UPLOAD_MB с voice=1 ---------------------------------------


@pytest.mark.asyncio
async def test_voice_over_max_upload_is_413_without_ffmpeg(
    client: AsyncClient, db_session: AsyncSession, auth_headers, upload_dir, ffmpeg_spy, monkeypatch
):
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    conv = await _make_conversation(db_session)
    too_big = b"\x1a\x45\xdf\xa3" + b"\x00" * (1024 * 1024)  # 1 МБ + 4 байта

    response = await _upload(
        client, auth_headers, conv.id, "Запись.webm", too_big, "audio/webm", voice=True
    )

    assert response.status_code == 413, response.text
    assert ffmpeg_spy == [], "проверка размера должна идти до перекодирования"
    assert _saved_files(upload_dir) == []

"""Тесты П3: метод Telegram для медиа, повтор через sendDocument, caption.

Внешние вызовы подменены: `telegram.call` (api.telegram.org), `telegram.send_message`
и `telegram.send_media` (в deliver_telegram), `db.mark_sent` / `db.mark_failed`.
Страховка: `telegram.call` по умолчанию падает с AssertionError, так что неподменённый
вызов Telegram не уходит в сеть, а проваливает тест.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

GATEWAY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GATEWAY_DIR))

# main.py при импорте открывает SQLite (db.connect) и telegram.py читает
# конфиг из TELEGRAM_CONFIG: уводим оба во временную папку.
_TMP = tempfile.mkdtemp(prefix="gateway-tests-")
os.environ["GATEWAY_DB"] = os.path.join(_TMP, "gateway.db")
os.environ["TELEGRAM_CONFIG"] = os.path.join(_TMP, "telegram.json")

from app import db, main, telegram  # noqa: E402
from app.telegram import TelegramError  # noqa: E402

CHAT = "123456"
URL_JPG = "https://cdn.test/a.jpg"
URL_PDF = "https://cdn.test/b.pdf"


class FakeCall:
    """Подмена telegram.call: запоминает (метод, параметры), может падать по методу."""

    def __init__(self, fail=None):
        self.calls: list[tuple[str, dict]] = []
        self.fail = dict(fail or {})

    async def __call__(self, method, **params):
        self.calls.append((method, params))
        error = self.fail.get(method)
        if error is not None:
            raise error
        return {"message_id": len(self.calls)}

    @property
    def methods(self) -> list[str]:
        return [method for method, _ in self.calls]


@pytest.fixture(autouse=True)
def block_telegram_network(monkeypatch):
    async def blocked(method, **params):
        raise AssertionError(f"Неподменённый вызов Telegram: {method}")

    monkeypatch.setattr(telegram, "call", blocked)
    monkeypatch.setattr(telegram, "bot_token", lambda: "test-token")
    monkeypatch.setattr(main, "connection", object())


@pytest.fixture
def telegram_api(monkeypatch):
    def install(fail=None) -> FakeCall:
        fake = FakeCall(fail)
        monkeypatch.setattr(telegram, "call", fake)
        return fake

    return install


# ---------------------------------------------------------------------------
# 1. Таблица «расширение → метод»
# ---------------------------------------------------------------------------

TABLE = [
    ("https://cdn.test/a.jpg", "sendPhoto", "photo"),
    ("https://cdn.test/a.jpeg", "sendPhoto", "photo"),
    ("https://cdn.test/a.png", "sendPhoto", "photo"),
    ("https://cdn.test/a.webp", "sendPhoto", "photo"),
    ("https://cdn.test/a.gif", "sendAnimation", "animation"),
    ("https://cdn.test/a.ogg", "sendVoice", "voice"),
    ("https://cdn.test/a.oga", "sendVoice", "voice"),
    ("https://cdn.test/a.opus", "sendVoice", "voice"),
    ("https://cdn.test/a.mp3", "sendAudio", "audio"),
    ("https://cdn.test/a.m4a", "sendAudio", "audio"),
    ("https://cdn.test/a.mp4", "sendVideo", "video"),
    ("https://cdn.test/a.mov", "sendVideo", "video"),
    ("https://cdn.test/a.pdf", "sendDocument", "document"),
    ("https://cdn.test/a.heic", "sendDocument", "document"),
    ("https://cdn.test/a.zip", "sendDocument", "document"),
    ("https://cdn.test/noext", "sendDocument", "document"),
    ("https://cdn.test/dir.jpg/file", "sendDocument", "document"),
]

UPPER_CASE = [
    ("https://cdn.test/A.JPG", "sendPhoto", "photo"),
    ("https://cdn.test/B.Png", "sendPhoto", "photo"),
    ("https://cdn.test/C.GIF", "sendAnimation", "animation"),
    ("https://cdn.test/D.OPUS", "sendVoice", "voice"),
    ("https://cdn.test/E.M4A", "sendAudio", "audio"),
    ("https://cdn.test/F.MOV", "sendVideo", "video"),
]

WITH_QUERY = [
    ("https://cdn.test/a.jpg?x=1", "sendPhoto", "photo"),
    ("https://cdn.test/a.MP3?token=abc&v=2", "sendAudio", "audio"),
    ("https://cdn.test/a.gif?x=1", "sendAnimation", "animation"),
    ("https://cdn.test/a.pdf?name=photo.jpg", "sendDocument", "document"),
    ("https://cdn.test/a.ogg?x=1#t=5", "sendVoice", "voice"),
    ("https://cdn.test/a.mp4#frag", "sendVideo", "video"),
]

ALL_CASES = TABLE + UPPER_CASE + WITH_QUERY


@pytest.mark.parametrize("url,method,key", ALL_CASES)
def test_media_method_by_extension(url, method, key):
    assert telegram._media_method(url) == (method, key)


@pytest.mark.asyncio
@pytest.mark.parametrize("url,method,key", ALL_CASES)
async def test_send_media_calls_method_for_extension(telegram_api, url, method, key):
    fake = telegram_api()
    await telegram.send_media(CHAT, url)
    assert fake.calls == [(method, {"chat_id": CHAT, key: url})]


# ---------------------------------------------------------------------------
# 2. Caption
# ---------------------------------------------------------------------------


def test_caption_limit_constant():
    assert telegram.CAPTION_LIMIT == 1024


@pytest.mark.asyncio
async def test_caption_sent_with_file(telegram_api):
    fake = telegram_api()
    await telegram.send_media(CHAT, URL_JPG, caption="Подпись")
    assert fake.calls == [
        ("sendPhoto", {"chat_id": CHAT, "photo": URL_JPG, "caption": "Подпись"})
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("caption", [None, ""])
async def test_caption_omitted_when_not_given(telegram_api, caption):
    fake = telegram_api()
    await telegram.send_media(CHAT, URL_PDF, caption=caption)
    assert "caption" not in fake.calls[0][1]


@pytest.mark.asyncio
@pytest.mark.parametrize("length", [1023, 1024])
async def test_caption_within_limit_not_truncated(telegram_api, length):
    fake = telegram_api()
    await telegram.send_media(CHAT, URL_PDF, caption="я" * length)
    assert fake.calls[0][1]["caption"] == "я" * length


@pytest.mark.asyncio
@pytest.mark.parametrize("length", [1025, 1500, 5000])
async def test_caption_truncated_to_limit(telegram_api, length):
    fake = telegram_api()
    await telegram.send_media(CHAT, URL_PDF, caption="я" * length)
    assert fake.calls[0][1]["caption"] == "я" * 1024


# ---------------------------------------------------------------------------
# 3. Повтор через sendDocument
# ---------------------------------------------------------------------------

RETRY_CASES = [
    ("https://cdn.test/a.jpg", "sendPhoto"),
    ("https://cdn.test/a.gif", "sendAnimation"),
    ("https://cdn.test/a.ogg", "sendVoice"),
    ("https://cdn.test/a.mp3", "sendAudio"),
    ("https://cdn.test/a.mp4", "sendVideo"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("url,method", RETRY_CASES)
async def test_failed_method_retried_as_document(telegram_api, url, method):
    fake = telegram_api(
        {method: TelegramError("Bad Request: wrong file format", status_code=400)}
    )
    result = await telegram.send_media(CHAT, url, caption="Текст")
    assert fake.methods == [method, "sendDocument"]
    assert fake.calls[1] == (
        "sendDocument",
        {"chat_id": CHAT, "document": url, "caption": "Текст"},
    )
    assert result == "2"


@pytest.mark.asyncio
async def test_retry_error_on_document_is_propagated_without_second_retry(telegram_api):
    fake = telegram_api(
        {
            "sendVoice": TelegramError("voice failed", status_code=400),
            "sendDocument": TelegramError("document failed", status_code=400),
        }
    )
    with pytest.raises(TelegramError, match="document failed"):
        await telegram.send_media(CHAT, "https://cdn.test/a.ogg")
    assert fake.methods == ["sendVoice", "sendDocument"]


@pytest.mark.asyncio
async def test_document_failure_is_not_retried(telegram_api):
    fake = telegram_api(
        {"sendDocument": TelegramError("Too Many Requests", status_code=429)}
    )
    with pytest.raises(TelegramError):
        await telegram.send_media(CHAT, URL_PDF)
    assert fake.methods == ["sendDocument"]


@pytest.mark.asyncio
async def test_non_telegram_error_is_not_retried(telegram_api):
    fake = telegram_api({"sendVoice": RuntimeError("boom")})
    with pytest.raises(RuntimeError):
        await telegram.send_media(CHAT, "https://cdn.test/a.ogg")
    assert fake.methods == ["sendVoice"]


@pytest.mark.asyncio
async def test_success_on_first_method_no_retry(telegram_api):
    fake = telegram_api()
    await telegram.send_media(CHAT, "https://cdn.test/a.ogg")
    assert fake.methods == ["sendVoice"]


# ---------------------------------------------------------------------------
# 4. deliver_telegram: решение «caption или send_message + файлы»
# ---------------------------------------------------------------------------


def make_row(media=None, text="Здравствуйте", row_id=7):
    return {
        "id": row_id,
        "source": "telegram",
        "chat_id": CHAT,
        "text": text,
        "media": None if media is None else json.dumps(media, ensure_ascii=False),
        "attempts": 0,
    }


@pytest.fixture
def outbox(monkeypatch):
    log = {"events": [], "sent": [], "failed": []}

    async def fake_send_message(chat_id, text):
        log["events"].append(("message", chat_id, text))
        return "1"

    async def fake_send_media(chat_id, url, caption=None):
        log["events"].append(("media", chat_id, url, caption))
        return "1"

    monkeypatch.setattr(telegram, "send_message", fake_send_message)
    monkeypatch.setattr(telegram, "send_media", fake_send_media)
    monkeypatch.setattr(
        db, "mark_sent", lambda conn, event_id: log["sent"].append(event_id)
    )
    monkeypatch.setattr(
        db,
        "mark_failed",
        lambda conn, event_id, error, retryable: log["failed"].append(
            (event_id, error, retryable)
        ),
    )
    return log


@pytest.mark.asyncio
async def test_single_file_short_text_is_one_caption_send(outbox):
    await main.deliver_telegram(make_row(media=[URL_JPG], text="Вот фото"))
    assert outbox["events"] == [("media", CHAT, URL_JPG, "Вот фото")]


@pytest.mark.asyncio
async def test_single_file_text_of_exactly_1024_uses_caption(outbox):
    text = "т" * 1024
    await main.deliver_telegram(make_row(media=[URL_JPG], text=text))
    assert outbox["events"] == [("media", CHAT, URL_JPG, text)]


@pytest.mark.asyncio
async def test_single_file_text_over_1024_sends_message_then_file_without_caption(outbox):
    text = "т" * 1025
    await main.deliver_telegram(make_row(media=[URL_PDF], text=text))
    assert outbox["events"] == [
        ("message", CHAT, text),
        ("media", CHAT, URL_PDF, None),
    ]


@pytest.mark.asyncio
async def test_two_files_send_message_then_two_files(outbox):
    await main.deliver_telegram(make_row(media=[URL_JPG, URL_PDF], text="Два файла"))
    assert outbox["events"] == [
        ("message", CHAT, "Два файла"),
        ("media", CHAT, URL_JPG, None),
        ("media", CHAT, URL_PDF, None),
    ]


@pytest.mark.asyncio
async def test_text_only_without_media(outbox):
    await main.deliver_telegram(make_row(media=None, text="Только текст"))
    assert outbox["events"] == [("message", CHAT, "Только текст")]


@pytest.mark.asyncio
async def test_empty_media_list_is_text_only(outbox):
    await main.deliver_telegram(make_row(media=[], text="Только текст"))
    assert outbox["events"] == [("message", CHAT, "Только текст")]


@pytest.mark.asyncio
async def test_empty_text_with_one_file_sends_no_empty_message(outbox):
    await main.deliver_telegram(make_row(media=[URL_PDF], text=""))
    assert outbox["events"] == [("media", CHAT, URL_PDF, None)]


@pytest.mark.asyncio
async def test_media_as_dict_with_url_is_accepted(outbox):
    await main.deliver_telegram(make_row(media=[{"url": URL_JPG}], text="Фото"))
    assert outbox["events"] == [("media", CHAT, URL_JPG, "Фото")]


@pytest.mark.asyncio
async def test_relative_link_appended_to_text_when_no_remote_files(outbox):
    link = "/uploads/messages/att-1/a.pdf"
    await main.deliver_telegram(make_row(media=[link], text="Смотрите"))
    assert outbox["events"] == [("message", CHAT, f"Смотрите\n{link}")]


@pytest.mark.asyncio
async def test_relative_link_with_empty_text_is_the_message(outbox):
    link = "/uploads/messages/att-1/a.pdf"
    await main.deliver_telegram(make_row(media=[link], text=""))
    assert outbox["events"] == [("message", CHAT, link)]


@pytest.mark.asyncio
async def test_relative_link_appended_into_caption_of_single_remote_file(outbox):
    link = "/uploads/messages/att-1/x.pdf"
    await main.deliver_telegram(make_row(media=[URL_JPG, link], text="Фото"))
    assert outbox["events"] == [("media", CHAT, URL_JPG, f"Фото\n{link}")]


@pytest.mark.asyncio
async def test_success_marks_row_sent(outbox):
    await main.deliver_telegram(make_row(media=[URL_JPG], text="Ок", row_id=42))
    assert outbox["sent"] == [42]
    assert outbox["failed"] == []


@pytest.mark.asyncio
async def test_text_only_success_marks_row_sent(outbox):
    await main.deliver_telegram(make_row(media=None, text="Ок", row_id=43))
    assert outbox["sent"] == [43]
    assert outbox["failed"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,retryable",
    [
        (TelegramError("Bad Request: chat not found", status_code=400), False),
        (TelegramError("Too Many Requests", status_code=429), True),
        (TelegramError("Telegram недоступен"), True),
    ],
)
async def test_telegram_error_marks_row_failed(outbox, monkeypatch, error, retryable):
    async def failing_send_media(chat_id, url, caption=None):
        raise error

    monkeypatch.setattr(telegram, "send_media", failing_send_media)
    await main.deliver_telegram(make_row(media=[URL_JPG], text="Ок", row_id=9))
    assert outbox["sent"] == []
    assert outbox["failed"] == [(9, str(error), retryable)]


@pytest.mark.asyncio
async def test_missing_bot_token_marks_failed_retryable(outbox, monkeypatch):
    monkeypatch.setattr(telegram, "bot_token", lambda: "")
    await main.deliver_telegram(make_row(media=[URL_JPG], text="Ок", row_id=5))
    assert outbox["events"] == []
    assert outbox["sent"] == []
    assert outbox["failed"][0][0] == 5
    assert outbox["failed"][0][2] is True

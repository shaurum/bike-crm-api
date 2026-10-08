"""Шлюз интеграций: очередь событий между облаком и локальной CRM."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app import avito, db, telegram

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("gateway")

API_TOKEN = os.environ.get("GATEWAY_TOKEN", "")
POLL_INTERVAL = float(os.environ.get("AVITO_POLL_INTERVAL", "60"))
SEND_INTERVAL = float(os.environ.get("OUTBOX_INTERVAL", "2"))
MAX_ATTEMPTS = int(os.environ.get("OUTBOX_MAX_ATTEMPTS", "10"))

connection = db.connect()

CALLBACK_HTML = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Подключение Авито — Шлюз интеграций</title>
<style>
  body { font: 16px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         max-width: 520px; margin: 64px auto; padding: 0 20px; color: #111; }
  h1 { font-size: 22px; margin-bottom: 8px; }
  #out { margin-top: 20px; padding: 16px; border: 1px solid #e3e3e3; border-radius: 10px;
         background: #fafafa; }
  .ok   { color: #0a7a3d; }
  .err  { color: #b3261e; }
  .hint { color: #666; font-size: 14px; }
</style>
</head>
<body>
<h1>Подключение Авито</h1>
<div id="out" class="hint">Проверяем данные от Авито…</div>
<script>
(function () {
  var out = document.getElementById('out');
  var p = new URLSearchParams(location.search);
  var code = p.get('code');
  var state = p.get('state');
  var err = p.get('error_description') || p.get('error');

  function esc(v) {
    return String(v).replace(/[&<>"]/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c];
    });
  }

  async function run() {
    if (err) { out.className = 'err'; out.textContent = 'Авито вернул ошибку: ' + err; return; }
    if (!code) { out.className = 'err'; out.textContent = 'В ответе нет code — откройте ссылку подключения из CRM.'; return; }
    try {
      var r = await fetch('/avito/callback', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code: code, state: state})
      });
      var d = await r.json().catch(function () { return {}; });
      if (!r.ok) {
        out.className = 'err';
        out.textContent = 'Не удалось подключить: ' + (d.detail || ('HTTP ' + r.status));
        return;
      }
      out.className = 'ok';
      out.innerHTML = 'Подключено! Аккаунт: <strong>' + esc(d.name || d.user_id || '') +
        '</strong><div class="hint" style="margin-top:8px">Можно закрыть вкладку и вернуться в CRM.</div>';
    } catch (e) {
      out.className = 'err';
      out.textContent = 'Сбой запроса: ' + e;
    }
  }
  run();
})();
</script>
</body>
</html>
"""


def require_token(authorization: Optional[str] = Header(None)) -> None:
    if not API_TOKEN:
        return
    expected = f"Bearer {API_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Неверный токен доступа")


class OutboxItem(BaseModel):
    source: str = Field("avito")
    chat_id: str
    text: str = Field(..., min_length=1, max_length=4000)


class OutboxBatch(BaseModel):
    items: list[OutboxItem]


class AvitoConfigPatch(BaseModel):
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: Optional[str] = None
    scopes: Optional[str] = None


class AvitoCallback(BaseModel):
    code: str
    state: Optional[str] = None


async def poll_avito() -> None:
    config = avito.load_config()
    user_id = config.get("user_id")
    if not user_id or not config.get("access_token"):
        return

    try:
        chats = await avito.list_chats(str(user_id))
    except avito.AvitoError as exc:
        logger.warning("Avito: список чатов недоступен: %s", exc)
        return
    except Exception:  # noqa: BLE001
        logger.exception("Avito: ошибка опроса чатов")
        return

    if not chats:
        return

    seen = dict(config.get("avito_seen") or {})
    updates: dict[str, int] = {}

    for chat in chats:
        chat_id = str(chat.get("id") or "")
        if not chat_id:
            continue
        last = chat.get("last_message") or {}
        if str(last.get("direction") or "") != "in":
            continue
        created = int(last.get("created") or 0)
        if created <= int(seen.get(chat_id) or 0):
            continue

        try:
            messages = await avito.list_messages(str(user_id), chat_id, limit=50)
        except avito.AvitoError as exc:
            logger.warning("Avito: чат %s не прочитан: %s", chat_id, exc)
            continue
        except Exception:  # noqa: BLE001
            logger.exception("Avito: ошибка чтения чата %s", chat_id)
            continue

        sender = avito.counterparty_id(chat, user_id) or chat_id
        name = avito.counterparty_name(chat, user_id)
        highest = created

        for message in messages:
            if str(message.get("direction") or "") != "in":
                continue
            external_id = str(message.get("id") or "")
            text = avito.message_text(message)
            if not external_id or not text:
                continue
            db.add_inbound(
                connection,
                source="avito",
                external_id=external_id,
                chat_id=chat_id,
                text=text,
                sender=sender,
                sender_name=name,
                occurred_at=_iso_from_unix(message.get("created")),
            )
            highest = max(highest, int(message.get("created") or 0))

        updates[chat_id] = max(highest, created)

    if updates:
        merged = dict(avito.load_config().get("avito_seen") or {})
        merged.update(updates)
        avito.save_config({"avito_seen": merged})


def _iso_from_unix(value: Any) -> Optional[str]:
    from datetime import datetime, timezone

    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


async def deliver_outbox() -> None:
    row = db.next_outbound(connection)
    if row is None:
        return
    if int(row["attempts"]) >= MAX_ATTEMPTS:
        db.mark_failed(
            connection, int(row["id"]), "Превышен лимит попыток доставки", retryable=False
        )
        return
    if row["source"] == "telegram":
        await deliver_telegram(row)
        return
    if row["source"] != "avito":
        db.mark_failed(
            connection,
            int(row["id"]),
            f"Источник «{row['source']}» на шлюзе пока не подключён",
            retryable=False,
        )
        return

    config = avito.load_config()
    user_id = config.get("user_id")
    if not user_id:
        db.mark_failed(
            connection, int(row["id"]), "Авито не подключён на шлюзе", retryable=True
        )
        return

    try:
        await avito.send_text(str(user_id), str(row["chat_id"]), str(row["text"]))
    except avito.AvitoError as exc:
        retryable = exc.status_code is None or exc.status_code >= 500
        logger.warning("Avito: не отправлено (id=%s): %s", row["id"], exc)
        if exc.status_code == 402:
            # Тариф не оплачен — исходящие заблокированы, помечаем для статусов
            avito.save_config(
                {"paywall": True, "paywall_at": datetime.now(timezone.utc).isoformat()}
            )
        db.mark_failed(connection, int(row["id"]), str(exc), retryable=retryable)
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Avito: сбой отправки (id=%s)", row["id"])
        db.mark_failed(connection, int(row["id"]), str(exc), retryable=True)
        return

    if avito.load_config().get("paywall"):
        avito.save_config({"paywall": False, "paywall_at": ""})
    db.mark_sent(connection, int(row["id"]))
    logger.info("Avito: отправлено (id=%s)", row["id"])


async def deliver_telegram(row: Any) -> None:
    if not telegram.bot_token():
        db.mark_failed(
            connection, int(row["id"]), "Telegram-бот не настроен на шлюзе", retryable=True
        )
        return
    try:
        await telegram.send_message(str(row["chat_id"]), str(row["text"]))
    except telegram.TelegramError as exc:
        retryable = exc.status_code is None or exc.status_code == 429 or exc.status_code >= 500
        logger.warning("Telegram: не отправлено (id=%s): %s", row["id"], exc)
        db.mark_failed(connection, int(row["id"]), str(exc), retryable=retryable)
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Telegram: сбой отправки (id=%s)", row["id"])
        db.mark_failed(connection, int(row["id"]), str(exc), retryable=True)
        return

    db.mark_sent(connection, int(row["id"]))
    logger.info("Telegram: отправлено (id=%s)", row["id"])


async def poll_telegram() -> None:
    """Long-polling getUpdates: одно «зависшее» соединение вместо секундных опросов."""
    offset = int(telegram.load_config().get("offset") or 0)
    updates = await telegram.get_updates(offset, timeout=50)
    if not updates:
        return

    for update in updates:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        user = message.get("from") or {}
        chat_id = str(chat.get("id") or "")
        message_id = message.get("message_id")
        text = telegram.message_text(message)
        if not chat_id or not message_id or user.get("is_bot") or not text:
            continue
        try:
            db.add_inbound(
                connection,
                source="telegram",
                external_id=f"{chat_id}:{message_id}",
                chat_id=chat_id,
                text=text,
                sender=str(user.get("id") or chat_id),
                sender_name=telegram.sender_name(message),
                username=user.get("username") or None,
                occurred_at=telegram.iso_from_unix(message.get("date")),
            )
        except Exception:  # noqa: BLE001
            logger.exception("Telegram: не разобрали update_id=%s", update.get("update_id"))

    last = int(updates[-1].get("update_id") or 0)
    if last:
        telegram.save_config({"offset": last + 1})


async def _poll_loop() -> None:
    while True:
        try:
            await poll_avito()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Avito: сбой цикла опроса")
        await asyncio.sleep(POLL_INTERVAL)


async def _send_loop() -> None:
    while True:
        try:
            await deliver_outbox()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Outbox: сбой цикла отправки")
        await asyncio.sleep(SEND_INTERVAL)


async def _telegram_loop() -> None:
    while True:
        try:
            if not telegram.bot_token():
                await asyncio.sleep(30)
                continue
            await poll_telegram()
        except asyncio.CancelledError:
            raise
        except telegram.TelegramError as exc:
            logger.warning("Telegram: long-polling сбоит: %s", exc)
            await asyncio.sleep(5)
        except Exception:  # noqa: BLE001
            logger.exception("Telegram: сбой цикла опроса")
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(_: FastAPI):
    poller = asyncio.create_task(_poll_loop())
    sender = asyncio.create_task(_send_loop())
    tg_poller = asyncio.create_task(_telegram_loop())
    logger.info("Gateway started (poll=%ss, send=%ss)", POLL_INTERVAL, SEND_INTERVAL)
    try:
        yield
    finally:
        poller.cancel()
        sender.cancel()
        tg_poller.cancel()
        await asyncio.gather(poller, sender, tg_poller, return_exceptions=True)


app = FastAPI(title="Integration Gateway", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "gateway"}


@app.get("/status", dependencies=[Depends(require_token)])
async def status() -> dict[str, Any]:
    config = avito.load_config()
    tg_configured = bool(telegram.bot_token())
    tg_username = telegram.load_config().get("username")
    if tg_configured and not tg_username:
        try:
            me = await telegram.get_me()
            tg_username = me.get("username")
            telegram.save_config({"username": tg_username})
        except telegram.TelegramError as exc:
            logger.warning("Telegram getMe не удался: %s", exc)
    return {
        "avito": {
            "configured": bool(config.get("client_id") and config.get("client_secret")),
            "connected": bool(config.get("access_token")),
            "user_id": config.get("user_id"),
            "account_name": config.get("account_name"),
            "account_phone": config.get("account_phone"),
            "token_expires_at": config.get("token_expires_at"),
            "redirect_uri": config.get("redirect_uri"),
            "paywall": bool(config.get("paywall")),
            "paywall_at": config.get("paywall_at"),
        },
        "telegram": {
            "configured": tg_configured,
            "username": tg_username,
        },
        "queue": db.stats(connection),
        "poll_interval": POLL_INTERVAL,
    }


@app.post("/avito/config", dependencies=[Depends(require_token)])
async def avito_config(payload: AvitoConfigPatch) -> dict[str, Any]:
    saved = avito.save_config(payload.model_dump())
    return {
        "configured": bool(saved.get("client_id") and saved.get("client_secret")),
        "redirect_uri": saved.get("redirect_uri"),
        "connected": bool(saved.get("access_token")),
    }


@app.post("/avito/connect-url", dependencies=[Depends(require_token)])
async def avito_connect_url() -> dict[str, str]:
    config = avito.load_config()
    client_id = config.get("client_id")
    redirect_uri = config.get("redirect_uri")
    if not client_id or not config.get("client_secret"):
        raise HTTPException(status_code=400, detail="Сначала сохраните client_id и client_secret")
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="Сначала сохраните redirect_uri")
    if not str(redirect_uri).startswith("https://"):
        raise HTTPException(status_code=400, detail="Авито принимает только redirect_uri по https")

    state = secrets.token_urlsafe(24)
    avito.save_config(
        {
            "pending_state": state,
            "pending_state_exp": (
                datetime.now(timezone.utc) + timedelta(minutes=15)
            ).isoformat(),
        }
    )
    return {
        "url": avito.build_connect_url(
            str(client_id),
            str(redirect_uri),
            str(config.get("scopes") or avito.DEFAULT_SCOPES),
            state,
        ),
        "redirect_uri": str(redirect_uri),
        "state": state,
    }


def _consume_state(state: Optional[str]) -> None:
    config = avito.load_config()
    expected = str(config.get("pending_state") or "")
    if not expected or not state or not secrets.compare_digest(expected, str(state)):
        raise HTTPException(
            status_code=400,
            detail="Неверный или неизвестный state — запустите подключение заново из CRM",
        )
    expiry = config.get("pending_state_exp")
    if expiry:
        try:
            moment = datetime.fromisoformat(str(expiry))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
        except ValueError:
            moment = None
        if moment and moment < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=400, detail="Время подключения истекло — повторите попытку"
            )
    avito.save_config({"pending_state": "", "pending_state_exp": ""})


@app.post("/avito/callback")
async def avito_callback(payload: AvitoCallback) -> dict[str, Any]:
    _consume_state(payload.state)
    try:
        await avito.exchange_code(payload.code)
        account = await avito.fetch_account()
    except avito.AvitoError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"connected": True, "user_id": account.get("id"), "name": account.get("name")}


@app.get("/avito/callback", response_class=HTMLResponse)
async def avito_callback_page() -> str:
    return CALLBACK_HTML


@app.post("/avito/refresh", dependencies=[Depends(require_token)])
async def avito_refresh() -> dict[str, Any]:
    try:
        saved = await avito.refresh_token()
    except avito.AvitoError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"connected": True, "token_expires_at": saved.get("token_expires_at")}


@app.post("/avito/disconnect", dependencies=[Depends(require_token)])
async def avito_disconnect() -> dict[str, Any]:
    config = avito.drop_tokens()
    return {
        "connected": False,
        "configured": bool(config.get("client_id") and config.get("client_secret")),
    }


@app.get("/events", dependencies=[Depends(require_token)])
async def events(
    after: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    items = db.pull_inbound(connection, after, limit)
    return {"events": items, "cursor": items[-1]["id"] if items else after}


@app.get("/telegram/resolve", dependencies=[Depends(require_token)])
async def telegram_resolve(username: str = Query(..., min_length=1)) -> dict[str, Any]:
    """Есть ли открытый чат с этим ником (пользователь писал боту)."""
    chat_id = db.resolve_chat(connection, "telegram", username)
    return {"found": bool(chat_id), "chat_id": chat_id}


@app.post("/outbox", dependencies=[Depends(require_token)])
async def outbox(payload: OutboxBatch) -> dict[str, Any]:
    ids = [
        db.enqueue_outbound(
            connection,
            source=item.source,
            chat_id=item.chat_id,
            text=item.text,
        )
        for item in payload.items
    ]
    return {"accepted": len(ids), "ids": ids}


@app.get("/outbox", dependencies=[Depends(require_token)])
async def outbox_list(
    status: str = Query("failed"), limit: int = Query(50, ge=1, le=200)
) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT id, source, chat_id, text, status, attempts, last_error, updated_at
        FROM event
        WHERE direction = 'outbound' AND status = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (status, limit),
    ).fetchall()
    return {"items": [dict(row) for row in rows]}


@app.post("/outbox/{event_id}/retry", dependencies=[Depends(require_token)])
async def outbox_retry(event_id: int) -> dict[str, Any]:
    if not db.retry(connection, event_id):
        raise HTTPException(status_code=404, detail="Событие не найдено")
    return {"retried": True, "id": event_id}

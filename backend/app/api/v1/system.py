"""Версия CRM и управление автообновлением.

Состояние пишут скрипты автообновления (scripts/auto-update.ps1 / auto-update.sh):
файл лежит в корне backend/ и виден контейнеру как /app/.update_state.json.
Режим (auto|manual) — backend/.update_mode; по умолчанию auto.
Запрос на установку — backend/.update_requested: «1» значит последнюю версию,
тег (v1.1.4) — конкретную; скрипт подхватывает его при следующем запуске.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.auth import get_current_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])

# backend/app/api/v1/system.py -> backend/ (корень смонтированного тома)
BACKEND_ROOT = Path(__file__).resolve().parents[3]
STATE_FILE = BACKEND_ROOT / ".update_state.json"
REQUEST_FILE = BACKEND_ROOT / ".update_requested"
MODE_FILE = BACKEND_ROOT / ".update_mode"
LOG_FILE = BACKEND_ROOT / ".update.log"

VALID_MODES = {"auto", "manual"}
TAG_RE = re.compile(r"^v[0-9A-Za-z._-]+$")
ACTIVE_STAGES = {"checking", "downloading", "extracting", "copying", "building", "migrating", "restarting"}

GITHUB_API = "https://api.github.com/repos/shaurum/bike-crm-api"
RELEASES_TTL = 600.0
# Скрипт запускается каждые 1–5 минут; дольше тишины — планировщик не работает
STALE_AFTER_SECONDS = 20 * 60
LOG_LINES = 60

_releases_cache: dict[str, Any] = {"at": 0.0, "items": None}
_changes_cache: dict[str, list[str]] = {}


class UpdateModeIn(BaseModel):
    mode: str


class InstallIn(BaseModel):
    tag: Optional[str] = None


def _read_state() -> Optional[dict[str, Any]]:
    try:
        if STATE_FILE.exists():
            # utf-8-sig: на Windows файл мог сохраниться с BOM
            return json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("system: не прочитано состояние обновления: %s", exc)
    return None


def _read_mode() -> str:
    try:
        if MODE_FILE.exists():
            mode = MODE_FILE.read_text(encoding="utf-8").strip()
            if mode in VALID_MODES:
                return mode
    except Exception as exc:  # noqa: BLE001
        logger.warning("system: не прочитан режим обновления: %s", exc)
    return "auto"


def _read_request() -> Optional[str]:
    """None — запроса нет; "latest" — последняя версия; иначе тег."""
    try:
        if REQUEST_FILE.exists():
            value = REQUEST_FILE.read_text(encoding="utf-8").strip()
            return value if TAG_RE.match(value) else "latest"
    except OSError:
        pass
    return None


def _parse_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_configured() -> bool:
    return STATE_FILE.exists() or (BACKEND_ROOT / ".git").exists()


def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    # Без токена GitHub даёт 60 запросов в час на IP: для списка версий хватает
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


async def _fetch_releases() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{GITHUB_API}/releases", params={"per_page": 30}, headers=_github_headers()
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=502, detail=f"GitHub не отдал список версий (HTTP {response.status_code})"
        )
    items = []
    for raw in response.json():
        tag = raw.get("tag_name") or ""
        if raw.get("draft") or not TAG_RE.match(tag):
            continue
        asset = next((a for a in raw.get("assets") or [] if str(a.get("name", "")).endswith(".zip")), None)
        items.append(
            {
                "tag": tag,
                "name": raw.get("name") or tag,
                "published_at": raw.get("published_at"),
                "prerelease": bool(raw.get("prerelease")),
                "url": raw.get("html_url"),
                "size": asset.get("size") if asset else None,
                "installable": asset is not None,
            }
        )
    return items


async def _releases(force: bool = False) -> list[dict[str, Any]]:
    now = time.monotonic()
    cached = _releases_cache["items"]
    if cached is not None and not force and now - _releases_cache["at"] < RELEASES_TTL:
        return cached
    try:
        items = await _fetch_releases()
    except (httpx.HTTPError, HTTPException) as exc:
        if cached is not None:
            logger.warning("system: список версий из кэша, GitHub недоступен: %s", exc)
            return cached
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=502, detail="GitHub недоступен, список версий не получен") from exc
    _releases_cache.update(at=now, items=items)
    return items


@router.get("/version")
async def current_version():
    state = _read_state() or {}
    request = _read_request()
    stage = state.get("stage") or "idle"
    updating = bool(state.get("updating")) or stage in ACTIVE_STAGES
    last_check = _parse_time(state.get("last_check"))
    stale = bool(
        last_check
        and (datetime.now(timezone.utc) - last_check).total_seconds() > STALE_AFTER_SECONDS
    )
    return {
        "current_sha": state.get("current_sha"),
        "current_date": state.get("current_date"),
        "current_tag": state.get("current_tag"),
        "remote_sha": state.get("remote_sha"),
        "update_available": bool(state.get("update_available")),
        "updating": updating,
        "last_check": state.get("last_check"),
        "auto_update": True,
        "configured": _is_configured(),
        "stale": stale,
        "mode": _read_mode(),
        "note": state.get("note"),
        # Установка: этап, общий прогресс 0–100 и детали скачивания
        "stage": stage,
        "progress": state.get("progress") or 0,
        "target_tag": state.get("target_tag"),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "error": state.get("error"),
        "download_percent": state.get("download_percent"),
        "download_bytes": state.get("download_bytes"),
        "download_total": state.get("download_total"),
        # Запрос ждёт следующего запуска скрипта
        "queued": request is not None and not updating,
        "queued_tag": request,
    }


@router.get("/releases")
async def list_releases(refresh: bool = False, current_user=Depends(get_current_user)):
    """Версии с GitHub: от новых к старым, с отметками текущей и последней."""
    items = await _releases(force=refresh)
    state = _read_state() or {}
    current = state.get("current_tag")
    latest = next((r["tag"] for r in items if not r["prerelease"]), None)
    return {
        "items": [{**r, "is_current": r["tag"] == current, "is_latest": r["tag"] == latest} for r in items],
        "latest": latest,
        "current": current,
    }


@router.get("/releases/{tag}/changes")
async def release_changes(tag: str, current_user=Depends(get_current_user)):
    """Что вошло в версию: заголовки коммитов относительно предыдущего релиза."""
    if not TAG_RE.match(tag):
        raise HTTPException(status_code=422, detail="Некорректная версия")
    if tag in _changes_cache:
        return {"tag": tag, "changes": _changes_cache[tag]}

    items = await _releases()
    tags = [r["tag"] for r in items]
    if tag not in tags:
        raise HTTPException(status_code=404, detail="Версия не найдена")
    index = tags.index(tag)
    previous = tags[index + 1] if index + 1 < len(tags) else None
    if not previous:
        return {"tag": tag, "changes": []}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{GITHUB_API}/compare/{previous}...{tag}", headers=_github_headers()
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="GitHub недоступен") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub не отдал изменения (HTTP {response.status_code})")

    changes = []
    for commit in response.json().get("commits") or []:
        subject = (commit.get("commit", {}).get("message") or "").splitlines()[0].strip()
        # Служебные коммиты автообновления и слияния ничего не говорят пользователю
        if not subject or subject.startswith(("Merge ", "chore: release")):
            continue
        changes.append(subject)
    # Состав релиза не меняется: кэшируем навсегда
    _changes_cache[tag] = changes
    return {"tag": tag, "changes": changes}


@router.get("/update-log")
async def update_log(current_user=Depends(require_admin)):
    """Последние строки журнала скрипта обновления."""
    try:
        if LOG_FILE.exists():
            lines = LOG_FILE.read_text(encoding="utf-8-sig", errors="replace").splitlines()
            return {"lines": lines[-LOG_LINES:]}
    except OSError as exc:
        logger.warning("system: журнал обновления не прочитан: %s", exc)
    return {"lines": []}


@router.post("/update-mode")
async def set_update_mode(payload: UpdateModeIn, current_user=Depends(require_admin)):
    """Режим обновления: auto — ставить сразу, manual — только по кнопке."""
    if payload.mode not in VALID_MODES:
        raise HTTPException(status_code=422, detail="mode должен быть auto или manual")
    try:
        MODE_FILE.write_text(payload.mode, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Не удалось сохранить режим: {exc}")
    logger.info("system: режим обновления → %s (user=%s)", payload.mode, current_user.email)
    return {"ok": True, "mode": payload.mode}


@router.post("/update-install")
async def install_version(payload: InstallIn, current_user=Depends(require_admin)):
    """Поставить выбранную версию (или последнюю, если tag не указан) при следующем запуске скрипта."""
    if not _is_configured():
        # На локальной разработке скрипт не запущен — сообщаем честно
        return {"ok": False, "detail": "Автообновление не настроено на этой машине"}

    state = _read_state() or {}
    if bool(state.get("updating")) or (state.get("stage") in ACTIVE_STAGES):
        raise HTTPException(status_code=409, detail="Уже идёт установка, дождитесь её окончания")

    tag = (payload.tag or "").strip() or None
    latest = None
    if tag:
        if not TAG_RE.match(tag):
            raise HTTPException(status_code=422, detail="Некорректная версия")
        try:
            items = await _releases()
        except HTTPException:
            items = []
        if items:
            found = next((r for r in items if r["tag"] == tag), None)
            if not found:
                raise HTTPException(status_code=404, detail=f"Версия {tag} не найдена на GitHub")
            if not found["installable"]:
                raise HTTPException(status_code=400, detail=f"В версии {tag} нет архива для установки")
            latest = next((r["tag"] for r in items if not r["prerelease"]), None)

    try:
        REQUEST_FILE.write_text(tag or "1", encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Не удалось запросить установку: {exc}")

    # Иначе в режиме «авто» скрипт сразу вернёт последнюю версию после отката
    mode_switched = False
    if tag and latest and tag != latest and _read_mode() == "auto":
        MODE_FILE.write_text("manual", encoding="utf-8")
        mode_switched = True

    logger.info("system: запрошена установка %s (user=%s)", tag or "последней версии", current_user.email)
    detail = f"Версия {tag or 'последняя'} будет установлена при следующем запуске автообновления (до 5 минут)"
    if mode_switched:
        detail += ". Режим переключён на «Вручную», чтобы CRM не обновилась обратно"
    return {"ok": True, "detail": detail, "mode_switched": mode_switched}


@router.post("/update-check")
async def request_update(current_user=Depends(require_admin)):
    """Старая кнопка «Проверить и установить»: последняя версия."""
    return await install_version(InstallIn(tag=None), current_user)


@router.post("/update-cancel")
async def cancel_request(current_user=Depends(require_admin)):
    """Отменить запрос, пока скрипт его не подхватил."""
    state = _read_state() or {}
    if bool(state.get("updating")) or (state.get("stage") in ACTIVE_STAGES):
        raise HTTPException(status_code=409, detail="Установка уже идёт, отменить нельзя")
    try:
        REQUEST_FILE.unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Не удалось отменить: {exc}")
    return {"ok": True}

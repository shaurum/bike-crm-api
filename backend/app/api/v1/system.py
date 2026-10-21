"""Версия CRM и управление автообновлением.

Состояние пишут скрипты автообновления (scripts/auto-update.ps1 / auto-update.sh):
файл лежит в корне backend/ и виден контейнеру как /app/.update_state.json.
Режим (auto|manual) — backend/.update_mode; по умолчанию auto.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])

# backend/app/api/v1/system.py -> backend/ (корень смонтированного тома)
BACKEND_ROOT = Path(__file__).resolve().parents[3]
STATE_FILE = BACKEND_ROOT / ".update_state.json"
REQUEST_FILE = BACKEND_ROOT / ".update_requested"
MODE_FILE = BACKEND_ROOT / ".update_mode"

VALID_MODES = {"auto", "manual"}


class UpdateModeIn(BaseModel):
    mode: str


def _read_state() -> Optional[dict[str, Any]]:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
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


@router.get("/version")
async def current_version():
    state = _read_state() or {}
    return {
        "current_sha": state.get("current_sha"),
        "current_date": state.get("current_date"),
        "current_tag": state.get("current_tag"),
        "remote_sha": state.get("remote_sha"),
        "update_available": bool(state.get("update_available")),
        "updating": bool(state.get("updating")),
        "last_check": state.get("last_check"),
        "auto_update": True,
        "mode": _read_mode(),
        "note": state.get("note"),
    }


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


@router.post("/update-check")
async def request_update(current_user=Depends(require_admin)):
    """Попросить скрипт применить обновление немедленно (в течение минуты)."""
    if not (BACKEND_ROOT / ".git").exists() and not STATE_FILE.exists():
        # На локальной разработке скрипт не запущен — сообщаем честно
        return {
            "ok": False,
            "detail": "Автообновление не настроено на этой машине",
        }
    try:
        REQUEST_FILE.write_text("1", encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Не удалось запросить обновление: {exc}")
    return {"ok": True, "detail": "Обновление будет применено в течение минуты"}

"""Версия CRM и запрос автообновления на сервере.

Состояние пишет cron-скрипт на хосте (scripts/auto-update.sh):
файл лежит в корне backend/ и виден контейнеру как /app/.update_state.json.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])

# backend/app/api/v1/system.py -> backend/ (корень смонтированного тома)
BACKEND_ROOT = Path(__file__).resolve().parents[3]
STATE_FILE = BACKEND_ROOT / ".update_state.json"
REQUEST_FILE = BACKEND_ROOT / ".update_requested"


def _read_state() -> Optional[dict[str, Any]]:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("system: не прочитано состояние обновления: %s", exc)
    return None


@router.get("/version")
async def current_version():
    state = _read_state() or {}
    return {
        "current_sha": state.get("current_sha"),
        "current_date": state.get("current_date"),
        "remote_sha": state.get("remote_sha"),
        "update_available": bool(state.get("update_available")),
        "updating": bool(state.get("updating")),
        "last_check": state.get("last_check"),
        "auto_update": True,
        "note": state.get("note"),
    }


@router.post("/update-check")
async def request_update(current_user=Depends(require_admin)):
    """Попросить cron применить обновление немедленно (в течение минуты)."""
    if not (BACKEND_ROOT / ".git").exists() and not STATE_FILE.exists():
        # На локальной разработке cron нет — сообщаем честно
        return {
            "ok": False,
            "detail": "Автообновление настроено только на сервере",
        }
    try:
        REQUEST_FILE.write_text("1", encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Не удалось запросить обновление: {exc}")
    return {"ok": True, "detail": "Обновление будет применено в течение минуты"}

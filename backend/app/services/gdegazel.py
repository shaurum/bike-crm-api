"""Клиент API мониторинга GDEGAZEL.RU: статус трекеров и история GPS."""

from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.services import runtime_settings

API_URL = "https://gdegazel.ru/gps/yii_main.php"
TIMEOUT = 20.0
# Статус всех трекеров один на все запросы CRM: не чаще раза в STATUS_TTL секунд
STATUS_TTL = 30.0
# Сообщение старше этого срока считаем потерей связи с трекером
ONLINE_WINDOW = timedelta(minutes=15)
# Быстрее не ездят даже на эвакуаторе: такие скачки — аномалии GPS из документации API
MAX_TRACK_KMH = 150.0
# Столько точек подряд в новом месте подтверждают, что байк и правда там
CONFIRM_POINTS = 3

ACCOUNT_OK = "ok"
ACCOUNT_NOT_CONFIGURED = "not_configured"
ACCOUNT_INVALID_TOKEN = "invalid_token"
ACCOUNT_PAYMENT_REQUIRED = "payment_required"
ACCOUNT_UNAVAILABLE = "unavailable"

_ACCOUNT_BY_STATUS = {401: ACCOUNT_INVALID_TOKEN, 402: ACCOUNT_PAYMENT_REQUIRED}

_MESSAGES = {
    401: "GDEGAZEL отклонил токен: проверьте его в Настройки → Ключи и токены",
    402: "GDEGAZEL требует оплату: баланс отрицательный больше 7 дней",
    403: "GDEGAZEL: нет разрешения на операцию",
    404: "GDEGAZEL: трекер не найден у этого пользователя",
    422: "GDEGAZEL: недопустимый интервал времени",
    429: "GDEGAZEL: слишком много запросов, повторите позже",
}

_status_cache: Optional[tuple[float, list[dict]]] = None
_status_lock = asyncio.Lock()


class GdegazelError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code

    @property
    def account_state(self) -> str:
        if self.status_code is None and not is_configured():
            return ACCOUNT_NOT_CONFIGURED
        return _ACCOUNT_BY_STATUS.get(self.status_code or 0, ACCOUNT_UNAVAILABLE)


def api_token() -> str:
    return runtime_settings.get("GDEGAZEL_API_TOKEN")


def is_configured() -> bool:
    return bool(api_token())


def reset_cache() -> None:
    global _status_cache
    _status_cache = None


async def _request(route: str, params: Optional[dict] = None) -> Any:
    if not is_configured():
        raise GdegazelError("GDEGAZEL не настроен: укажите токен в Настройки → Ключи и токены")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                API_URL,
                headers={"x-gdegazel-api-token": api_token()},
                params={"r": f"api/{route}", **(params or {})},
            )
    except httpx.HTTPError as exc:
        # Текст исключения без заголовков: токен в сообщение не попадает
        raise GdegazelError(f"GDEGAZEL недоступен: {type(exc).__name__}") from exc

    if response.status_code != 200:
        message = _MESSAGES.get(
            response.status_code, f"GDEGAZEL временно недоступен (HTTP {response.status_code})"
        )
        raise GdegazelError(message, status_code=response.status_code)

    try:
        body = response.json()
    except ValueError as exc:
        raise GdegazelError("GDEGAZEL вернул не JSON", status_code=502) from exc
    if not isinstance(body, dict) or not body.get("ok"):
        raise GdegazelError("GDEGAZEL отклонил запрос", status_code=502)
    return body.get("result")


async def trackers_status() -> list[dict]:
    """Статус всех трекеров пользователя с коротким кэшем."""
    global _status_cache

    async with _status_lock:
        now = time.monotonic()
        if _status_cache and now - _status_cache[0] < STATUS_TTL:
            return _status_cache[1]
        result = await _request("trackers_status")
        trackers = result if isinstance(result, list) else []
        _status_cache = (now, trackers)
        return trackers


async def gps_log(tracker_id: int, start: datetime, end: datetime) -> list[dict]:
    """История GPS за интервал. Часовой пояс указываем явно, как советует документация."""
    result = await _request(
        "gps_log",
        {
            "tracker_id": tracker_id,
            "datetime_from": _format_time(start),
            "datetime_to": _format_time(end),
        },
    )
    return result if isinstance(result, list) else []


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")


def parse_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def has_position(latitude: Any, longitude: Any) -> bool:
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return False
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return False
    return not (latitude == 0 and longitude == 0)


def to_position(raw: dict, now: Optional[datetime] = None) -> dict:
    """Поля статуса, нужные CRM. ICCID, IMEI и базовые станции наружу не отдаём."""
    now = now or datetime.now(timezone.utc)
    reception = parse_time(raw.get("reception_time"))
    gps_time = parse_time(raw.get("gps_time"))
    located = has_position(raw.get("latitude"), raw.get("longitude"))

    return {
        "tracker_id": raw.get("tracker_id"),
        "title": raw.get("title"),
        "note": raw.get("note"),
        "latitude": raw.get("latitude") if located else None,
        "longitude": raw.get("longitude") if located else None,
        "speed": raw.get("speed"),
        "azimuth": raw.get("azimuth"),
        "satellites": raw.get("sat_num"),
        "ignition": raw.get("acc"),
        "moving": raw.get("car_move_status"),
        "shock_alarm": raw.get("shock_alarm"),
        "engine_locked": raw.get("relay_state"),
        "external_power": raw.get("external_power"),
        "external_voltage": raw.get("external_voltage"),
        "tracker_battery": raw.get("battery_state"),
        "gps_time": gps_time,
        "reception_time": reception,
        "online": reception is not None and now - reception <= ONLINE_WINDOW,
    }


def _distance_km(a: dict, b: dict) -> float:
    lat1, lon1 = math.radians(a["latitude"]), math.radians(a["longitude"])
    lat2, lon2 = math.radians(b["latitude"]), math.radians(b["longitude"])
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _is_plausible_step(previous: dict, point: dict) -> bool:
    distance = _distance_km(previous, point)
    hours = (point["_time"] - previous["_time"]).total_seconds() / 3600
    if hours <= 0:
        return distance < 0.2
    return distance / hours <= MAX_TRACK_KMH


def clean_track(raw_points: list[dict]) -> tuple[list[dict], int]:
    """Убирает из истории точки без координат и «телепортации». Возвращает точки и число отброшенных."""
    candidates = []
    for raw in raw_points:
        when = parse_time(raw.get("gps_time"))
        if when is None or not has_position(raw.get("latitude"), raw.get("longitude")):
            continue
        candidates.append({**raw, "_time": when})

    kept: list[dict] = []
    suspects: list[dict] = []
    for point in candidates:
        if not kept or _is_plausible_step(kept[-1], point):
            kept.append(point)
            suspects = []
            continue
        if suspects and not _is_plausible_step(suspects[-1], point):
            suspects = []
        suspects.append(point)
        if len(suspects) >= CONFIRM_POINTS:
            # Несколько точек подряд согласованы между собой — это реальное перемещение
            kept.extend(suspects)
            suspects = []

    points = [
        {
            "latitude": p["latitude"],
            "longitude": p["longitude"],
            "speed": p.get("speed"),
            "time": p["_time"],
        }
        for p in kept
    ]
    return points, len(raw_points) - len(points)

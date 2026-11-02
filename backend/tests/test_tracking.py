"""Трекеры GDEGAZEL: все обращения к внешнему API подменены."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio

from app.models import Bike, Branch
from app.services import gdegazel


def _status(tracker_id=5766, **extra):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")
    return {
        "tracker_id": tracker_id,
        "imei": "0097564",
        "iccid": "897010230573651106",
        "title": str(tracker_id),
        "note": None,
        "latitude": 54.945434,
        "longitude": 73.254493,
        "speed": 12,
        "battery_state": 91,
        "external_voltage": 52.4,
        "sat_num": 12,
        "gps_time": now,
        "reception_time": now,
        **extra,
    }


def _mock_api(monkeypatch, handler):
    real_client = httpx.AsyncClient

    def factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(gdegazel.httpx, "AsyncClient", factory)


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("GDEGAZEL_API_TOKEN", "test-token")
    gdegazel.reset_cache()
    yield
    gdegazel.reset_cache()


@pytest_asyncio.fixture
async def bike(db_session):
    branch = Branch(name="Тест", address="Адрес")
    db_session.add(branch)
    await db_session.flush()
    item = Bike(branch_id=branch.id, model="Maikaline U2", tracker_id=5766)
    db_session.add(item)
    await db_session.commit()
    return item


async def test_status_sends_token_header_and_caches(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"ok": True, "result": [_status()]})

    _mock_api(monkeypatch, handler)
    await gdegazel.trackers_status()
    await gdegazel.trackers_status()

    assert len(calls) == 1
    assert calls[0].headers["x-gdegazel-api-token"] == "test-token"
    assert calls[0].url.params["r"] == "api/trackers_status"


@pytest.mark.parametrize(
    "code,state",
    [
        (401, gdegazel.ACCOUNT_INVALID_TOKEN),
        (402, gdegazel.ACCOUNT_PAYMENT_REQUIRED),
        (503, gdegazel.ACCOUNT_UNAVAILABLE),
    ],
)
async def test_errors_map_to_account_state(monkeypatch, code, state):
    _mock_api(monkeypatch, lambda request: httpx.Response(code, text="<html>"))
    with pytest.raises(gdegazel.GdegazelError) as exc:
        await gdegazel.trackers_status()
    assert exc.value.account_state == state


async def test_missing_token_is_not_configured(monkeypatch):
    monkeypatch.delenv("GDEGAZEL_API_TOKEN")
    with pytest.raises(gdegazel.GdegazelError) as exc:
        await gdegazel.trackers_status()
    assert exc.value.account_state == gdegazel.ACCOUNT_NOT_CONFIGURED


async def test_gps_log_sends_explicit_utc_interval(monkeypatch):
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, json={"ok": True, "result": []})

    _mock_api(monkeypatch, handler)
    start = datetime(2026, 11, 1, 10, 0, tzinfo=timezone(timedelta(hours=3)))
    await gdegazel.gps_log(5766, start, start + timedelta(hours=1))

    assert seen["datetime_from"] == "2026-11-01 07:00:00+00"
    assert seen["datetime_to"] == "2026-11-01 08:00:00+00"


def test_position_hides_sim_data_and_zero_coordinates():
    position = gdegazel.to_position(_status(latitude=0, longitude=0))
    assert position["latitude"] is None and position["longitude"] is None
    assert "iccid" not in position and "imei" not in position


def test_position_offline_after_window():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    raw = _status(reception_time="2026-11-02 11:50:00+00")
    assert gdegazel.to_position(raw, now)["online"] is True
    assert gdegazel.to_position(raw, now + timedelta(minutes=20))["online"] is False


def _point(minute, lat=54.9, lon=73.4):
    return {"gps_time": f"2026-11-02 10:{minute:02d}:00+00", "latitude": lat, "longitude": lon}


def test_clean_track_drops_teleport_and_empty_points():
    raw = [
        _point(0),
        _point(1, lat=54.901),
        _point(2, lat=55.97, lon=37.41),  # «телепортация» в аэропорт
        _point(3, lat=54.902),
        {"gps_time": "2026-11-02 10:04:00+00", "latitude": None, "longitude": None},
    ]
    points, dropped = gdegazel.clean_track(raw)
    assert [p["latitude"] for p in points] == [54.9, 54.901, 54.902]
    assert dropped == 2


def test_clean_track_accepts_confirmed_move():
    raw = [_point(0), _point(1, lat=56.0), _point(2, lat=56.001), _point(3, lat=56.002)]
    points, dropped = gdegazel.clean_track(raw)
    assert len(points) == 4 and dropped == 0


async def test_fleet_returns_bound_and_unbound(client, auth_headers, bike, monkeypatch):
    _mock_api(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"ok": True, "result": [_status(), _status(tracker_id=9999)]}
        ),
    )
    response = await client.get("/api/v1/tracking/fleet", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["account"]["state"] == "ok"
    assert body["bikes"][0]["position"]["tracker_battery"] == 91
    assert [t["tracker_id"] for t in body["unbound_trackers"]] == [9999]


async def test_fleet_survives_payment_required(client, auth_headers, bike, monkeypatch):
    _mock_api(monkeypatch, lambda request: httpx.Response(402, json={"ok": False}))
    response = await client.get("/api/v1/tracking/fleet", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["account"]["state"] == "payment_required"
    assert body["bikes"][0]["position"] is None


async def test_fleet_requires_auth(client):
    response = await client.get("/api/v1/tracking/fleet")
    assert response.status_code in (401, 403)


async def test_tracker_cannot_be_bound_twice_and_is_freed_on_delete(
    client, auth_headers, bike, db_session
):
    other = Bike(branch_id=bike.branch_id, model="Другой")
    db_session.add(other)
    await db_session.commit()

    url = f"/api/v1/bikes/{other.id}"
    response = await client.patch(url, json={"tracker_id": 5766}, headers=auth_headers)
    assert response.status_code == 409

    await client.delete(f"/api/v1/bikes/{bike.id}", headers=auth_headers)
    response = await client.patch(url, json={"tracker_id": 5766}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["tracker_id"] == 5766


async def test_track_without_tracker_is_conflict(client, auth_headers, bike, db_session):
    bike.tracker_id = None
    await db_session.commit()
    response = await client.get(f"/api/v1/tracking/bikes/{bike.id}/track", headers=auth_headers)
    assert response.status_code == 409


async def test_track_rejects_interval_over_a_day(client, auth_headers, bike):
    response = await client.get(
        f"/api/v1/tracking/bikes/{bike.id}/track", params={"hours": 25}, headers=auth_headers
    )
    assert response.status_code == 422

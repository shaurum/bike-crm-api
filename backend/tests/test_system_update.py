"""Вкладка «Обновление»: версия и этапы из файла скрипта, список релизов, выбор версии."""

import json

import httpx
import pytest
from httpx import AsyncClient

from app.api.v1 import system

RELEASES = [
    {"tag_name": "v1.1.6", "name": "v1.1.6", "published_at": "2026-11-05T09:39:42Z", "draft": False,
     "prerelease": False, "html_url": "https://github.com/x/releases/v1.1.6",
     "assets": [{"name": "bike-crm-v1.1.6.zip", "size": 3149407}]},
    {"tag_name": "v1.1.5", "name": "v1.1.5", "published_at": "2026-10-26T14:40:39Z", "draft": False,
     "prerelease": False, "html_url": "https://github.com/x/releases/v1.1.5",
     "assets": [{"name": "bike-crm-v1.1.5.zip", "size": 368062}]},
    {"tag_name": "v1.1.4", "name": "v1.1.4", "published_at": "2026-10-26T13:26:00Z", "draft": False,
     "prerelease": False, "html_url": "https://github.com/x/releases/v1.1.4", "assets": []},
]
COMPARE = {"commits": [
    {"commit": {"message": "feat: карта байков\n\nподробности"}},
    {"commit": {"message": "Merge branch 'feature'"}},
    {"commit": {"message": "chore: release v1.1.5"}},
]}


@pytest.fixture(autouse=True)
def _files(tmp_path, monkeypatch):
    for name, filename in (
        ("STATE_FILE", ".update_state.json"),
        ("REQUEST_FILE", ".update_requested"),
        ("MODE_FILE", ".update_mode"),
        ("LOG_FILE", ".update.log"),
    ):
        monkeypatch.setattr(system, name, tmp_path / filename)
    system._releases_cache.update(at=0.0, items=None)
    system._changes_cache.clear()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/releases"):
            return httpx.Response(200, json=RELEASES)
        if "/compare/" in request.url.path:
            return httpx.Response(200, json=COMPARE)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(system.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw))
    return calls


def _state(**fields):
    base = {"current_tag": "v1.1.5", "remote_sha": "v1.1.6", "update_available": True,
            "updating": False, "last_check": "2099-01-01T00:00:00Z", "stage": "idle"}
    base.update(fields)
    # Windows-скрипт мог записать файл с BOM
    system.STATE_FILE.write_text(json.dumps(base), encoding="utf-8-sig")


async def test_version_reports_stage_and_queue(client: AsyncClient, auth_headers):
    _state(stage="downloading", progress=20, target_tag="v1.1.6", download_percent=50,
           download_bytes=10, download_total=20, updating=True)
    body = (await client.get("/api/v1/system/version", headers=auth_headers)).json()
    assert body["stage"] == "downloading"
    assert body["updating"] is True
    assert body["download_percent"] == 50
    assert body["queued"] is False

    _state()
    system.REQUEST_FILE.write_text("v1.1.4", encoding="utf-8")
    body = (await client.get("/api/v1/system/version", headers=auth_headers)).json()
    assert body["queued"] is True and body["queued_tag"] == "v1.1.4"
    assert body["stale"] is False


async def test_stale_when_script_silent(client: AsyncClient, auth_headers):
    _state(last_check="2020-01-01T00:00:00Z")
    body = (await client.get("/api/v1/system/version", headers=auth_headers)).json()
    assert body["stale"] is True


async def test_releases_marks_current_and_latest(client: AsyncClient, auth_headers):
    _state()
    body = (await client.get("/api/v1/system/releases", headers=auth_headers)).json()
    assert [r["tag"] for r in body["items"]] == ["v1.1.6", "v1.1.5", "v1.1.4"]
    by_tag = {r["tag"]: r for r in body["items"]}
    assert by_tag["v1.1.6"]["is_latest"] and not by_tag["v1.1.6"]["is_current"]
    assert by_tag["v1.1.5"]["is_current"]
    assert by_tag["v1.1.4"]["installable"] is False


async def test_changes_skip_service_commits(client: AsyncClient, auth_headers, _files):
    _state()
    body = (await client.get("/api/v1/system/releases/v1.1.6/changes", headers=auth_headers)).json()
    assert body["changes"] == ["feat: карта байков"]
    await client.get("/api/v1/system/releases/v1.1.6/changes", headers=auth_headers)
    assert sum("/compare/" in path for path in _files) == 1


async def test_install_older_version_switches_to_manual(client: AsyncClient, auth_headers):
    _state(current_tag="v1.1.6")
    response = await client.post(
        "/api/v1/system/update-install", headers=auth_headers, json={"tag": "v1.1.5"}
    )
    body = response.json()
    assert response.status_code == 200 and body["ok"] and body["mode_switched"]
    assert system.REQUEST_FILE.read_text(encoding="utf-8") == "v1.1.5"
    assert system.MODE_FILE.read_text(encoding="utf-8") == "manual"


async def test_install_latest_keeps_mode(client: AsyncClient, auth_headers):
    _state()
    body = (await client.post("/api/v1/system/update-install", headers=auth_headers, json={})).json()
    assert body["ok"] and not body["mode_switched"]
    assert system.REQUEST_FILE.read_text(encoding="utf-8") == "1"
    assert not system.MODE_FILE.exists()


async def test_install_rejects_unknown_busy_and_broken(client: AsyncClient, auth_headers):
    _state()
    unknown = await client.post("/api/v1/system/update-install", headers=auth_headers, json={"tag": "v9.9.9"})
    assert unknown.status_code == 404
    no_zip = await client.post("/api/v1/system/update-install", headers=auth_headers, json={"tag": "v1.1.4"})
    assert no_zip.status_code == 400

    _state(stage="building", updating=True)
    busy = await client.post("/api/v1/system/update-install", headers=auth_headers, json={})
    assert busy.status_code == 409


async def test_cancel_and_log(client: AsyncClient, auth_headers):
    _state()
    system.REQUEST_FILE.write_text("1", encoding="utf-8")
    assert (await client.post("/api/v1/system/update-cancel", headers=auth_headers)).status_code == 200
    assert not system.REQUEST_FILE.exists()

    system.LOG_FILE.write_text("\n".join(f"строка {i}" for i in range(100)), encoding="utf-8")
    lines = (await client.get("/api/v1/system/update-log", headers=auth_headers)).json()["lines"]
    assert len(lines) == system.LOG_LINES and lines[-1] == "строка 99"

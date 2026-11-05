"""Ключи и токены в настройках: только админ, секреты не утекают, значение главнее .env."""

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models import User, UserRole
from app.services import gateway, gdegazel, runtime_settings


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    for name in ("GDEGAZEL_API_TOKEN", "GATEWAY_URL", "GATEWAY_TOKEN", "PUBLIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    runtime_settings.reset_cache()
    gdegazel.reset_cache()
    yield
    # Кэш процесса живёт 30 секунд: следующие тесты не должны увидеть наши значения
    runtime_settings.reset_cache()
    gdegazel.reset_cache()


def _keys(body: dict) -> dict:
    return {item["name"]: item for item in body["keys"]}


async def test_manager_has_no_access(client: AsyncClient, db_session):
    manager = User(
        email="manager@test.local",
        hashed_password=get_password_hash("manager-password-1"),
        full_name="Менеджер",
        role=UserRole.MANAGER,
        is_active=True,
    )
    db_session.add(manager)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(manager.id)})}"}

    assert (await client.get("/api/v1/settings/runtime", headers=headers)).status_code == 403
    response = await client.patch(
        "/api/v1/settings/runtime", headers=headers, json={"values": {"GDEGAZEL_API_TOKEN": "x"}}
    )
    assert response.status_code == 403


async def test_secret_is_saved_but_never_returned(client: AsyncClient, auth_headers):
    response = await client.patch(
        "/api/v1/settings/runtime",
        headers=auth_headers,
        json={"values": {"GDEGAZEL_API_TOKEN": "  secret-from-ui  "}},
    )
    assert response.status_code == 200
    assert "secret-from-ui" not in response.text
    state = _keys(response.json())["GDEGAZEL_API_TOKEN"]
    assert state["source"] == "settings"
    assert state["value"] is None

    assert gdegazel.api_token() == "secret-from-ui"
    listing = await client.get("/api/v1/settings/runtime", headers=auth_headers)
    assert "secret-from-ui" not in listing.text


async def test_value_overrides_env_and_clear_returns_to_env(
    client: AsyncClient, auth_headers, monkeypatch
):
    monkeypatch.setenv("GATEWAY_URL", "https://env-gateway.example")
    await client.patch(
        "/api/v1/settings/runtime",
        headers=auth_headers,
        json={"values": {"GATEWAY_URL": "https://ui-gateway.example/", "GATEWAY_TOKEN": "tok"}},
    )
    assert gateway.gateway_url() == "https://ui-gateway.example"
    assert gateway.is_configured()

    response = await client.patch(
        "/api/v1/settings/runtime", headers=auth_headers, json={"clear": ["GATEWAY_URL"]}
    )
    state = _keys(response.json())["GATEWAY_URL"]
    assert state["source"] == "env"
    assert state["value"] == "https://env-gateway.example"
    assert gateway.gateway_url() == "https://env-gateway.example"


async def test_settings_fields_see_override(client: AsyncClient, auth_headers):
    before = settings.PUBLIC_BASE_URL
    await client.patch(
        "/api/v1/settings/runtime",
        headers=auth_headers,
        json={"values": {"PUBLIC_BASE_URL": "https://crm.example.com"}},
    )
    assert settings.PUBLIC_BASE_URL == "https://crm.example.com"

    await client.patch(
        "/api/v1/settings/runtime", headers=auth_headers, json={"clear": ["PUBLIC_BASE_URL"]}
    )
    assert settings.PUBLIC_BASE_URL == before


async def test_other_process_reads_value_from_db(client: AsyncClient, auth_headers):
    await client.patch(
        "/api/v1/settings/runtime",
        headers=auth_headers,
        json={"values": {"GDEGAZEL_API_TOKEN": "from-db"}},
    )
    # Как будто это другой воркер: своего кэша нет, значение читается из БД
    runtime_settings.reset_cache()
    assert gdegazel.api_token() == "from-db"


async def test_validation(client: AsyncClient, auth_headers):
    bad_url = await client.patch(
        "/api/v1/settings/runtime",
        headers=auth_headers,
        json={"values": {"PUBLIC_BASE_URL": "crm.example.com"}},
    )
    assert bad_url.status_code == 400

    unknown = await client.patch(
        "/api/v1/settings/runtime", headers=auth_headers, json={"values": {"SECRET_KEY": "x"}}
    )
    assert unknown.status_code == 400


async def test_storage_row_is_not_listed_as_integration(client: AsyncClient, auth_headers):
    await client.patch(
        "/api/v1/settings/runtime",
        headers=auth_headers,
        json={"values": {"GDEGAZEL_API_TOKEN": "x"}},
    )
    names = [i["name"] for i in (await client.get("/api/v1/settings/integrations", headers=auth_headers)).json()]
    assert runtime_settings.STORAGE_NAME not in names


async def test_health_reports_gdegazel(client: AsyncClient, auth_headers):
    response = await client.get("/api/v1/health/services", headers=auth_headers)
    assert response.status_code == 200
    service = next(s for s in response.json()["services"] if s["key"] == "gdegazel")
    assert service["status"] == "off"
    assert service["detail"] == "токен не задан"

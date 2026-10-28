from tests.conftest import ADMIN_PASSWORD


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_me_without_token(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_me_with_token(client, admin_user, auth_headers):
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == admin_user.email


async def test_login(client, admin_user):
    wrong = await client.post(
        "/api/v1/auth/login",
        data={"username": admin_user.email, "password": "wrong-password"},
    )
    assert wrong.status_code == 401

    ok = await client.post(
        "/api/v1/auth/login",
        data={"username": admin_user.email, "password": ADMIN_PASSWORD},
    )
    assert ok.status_code == 200
    assert "access_token" in ok.json()

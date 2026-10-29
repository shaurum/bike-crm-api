import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Customer, User, UserRole
from app.core.security import get_password_hash


async def test_db_session_points_to_test_database(db_session: AsyncSession):
    """Фикстура db_session должна работать только с тестовой БД bike_crm_test."""
    assert settings.POSTGRES_DB == "bike_crm_test"
    result = await db_session.execute(text("select current_database()"))
    assert result.scalar_one() == "bike_crm_test"


async def test_isolation_1_creates_user(db_session: AsyncSession):
    """Первый тест: на старте база пуста, создаём второго пользователя."""
    count_before = await db_session.scalar(select(func.count()).select_from(User))
    assert count_before == 0

    second = User(
        email="isolation@test.local",
        hashed_password=get_password_hash("isolation-password"),
        full_name="Второй пользователь",
        role=UserRole.MANAGER,
        is_active=True,
    )
    db_session.add(second)
    await db_session.commit()

    count_after = await db_session.scalar(select(func.count()).select_from(User))
    assert count_after == 1


async def test_isolation_2_does_not_see_previous_user(db_session: AsyncSession):
    """Второй тест идёт сразу за предыдущим: запись из него должна быть очищена."""
    count = await db_session.scalar(select(func.count()).select_from(User))
    assert count == 0

    found = await db_session.execute(select(User).where(User.email == "isolation@test.local"))
    assert found.scalar_one_or_none() is None


@pytest.mark.parametrize("path", ["/api/v1/bikes", "/api/v1/customers"])
async def test_protected_list_with_auth_headers(client, auth_headers, path):
    """Защищённые списки отвечают 200 с токеном администратора."""
    response = await client.get(path, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_client_sees_data_from_db_session(client, auth_headers, db_session: AsyncSession):
    """Данные, записанные через db_session, видны в ответе API: override get_db работает."""
    db_session.add(Customer(full_name="Клиент для проверки изоляции"))
    await db_session.commit()

    response = await client.get("/api/v1/customers", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["full_name"] == "Клиент для проверки изоляции"

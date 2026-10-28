"""Клиенты: валидация даты рождения (PLAN.md, П4).

Валидатор стоит только на входящих схемах CustomerCreate и CustomerUpdate:
- None или дата в диапазоне [01.01.1900, сегодня] допустимы;
- иначе 422 с текстом «Дата рождения должна быть между ...».
Старые некорректные данные в БД читаются через response-схемы (GET) и не блокируют правку других полей.
"""

from datetime import date, timedelta
from typing import Optional
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer

CUSTOMERS_URL = "/api/v1/customers"
BIRTH_DATE_ERROR = "Дата рождения должна быть между"

TODAY = date.today()
TOMORROW = TODAY + timedelta(days=1)

INVALID_BIRTH_DATES = [
    pytest.param("1299-11-21", id="year_1299"),
    pytest.param(TOMORROW.isoformat(), id="tomorrow"),
    pytest.param("1899-12-31", id="before_min"),
]

VALID_BIRTH_DATES = [
    pytest.param("1990-05-01", id="regular"),
    pytest.param(TODAY.isoformat(), id="today"),
    pytest.param(None, id="null"),
]


async def _insert_customer(
    db_session: AsyncSession,
    birth_date: Optional[date],
    phone: str = "+79002223344",
    full_name: str = "Иванов Иван Иванович",
) -> Customer:
    """Клиент, вставленный напрямую в БД (минуя валидацию API)."""
    customer = Customer(full_name=full_name, phone=phone, birth_date=birth_date)
    db_session.add(customer)
    await db_session.commit()
    return customer


def _assert_birth_date_422(response) -> None:
    assert response.status_code == 422, response.text
    assert BIRTH_DATE_ERROR in str(response.json()["detail"])


# ------------------------------------------------------------------
# Создание клиента: POST /api/v1/customers
# ------------------------------------------------------------------


@pytest.mark.parametrize("birth_date", INVALID_BIRTH_DATES)
async def test_create_invalid_birth_date_returns_422(client: AsyncClient, auth_headers, birth_date):
    response = await client.post(
        CUSTOMERS_URL,
        headers=auth_headers,
        json={"full_name": "Тест Клиент", "phone": "+79001110001", "birth_date": birth_date},
    )
    _assert_birth_date_422(response)


@pytest.mark.parametrize("birth_date", VALID_BIRTH_DATES)
async def test_create_valid_birth_date_is_saved(
    client: AsyncClient, db_session: AsyncSession, auth_headers, birth_date
):
    response = await client.post(
        CUSTOMERS_URL,
        headers=auth_headers,
        json={"full_name": "Тест Клиент", "phone": "+79001110002", "birth_date": birth_date},
    )
    assert 200 <= response.status_code < 300, response.text
    assert response.json()["birth_date"] == birth_date

    # Дата действительно записана в БД
    db_session.expire_all()
    customer = (
        await db_session.execute(select(Customer).where(Customer.id == UUID(response.json()["id"])))
    ).scalar_one()
    expected = date.fromisoformat(birth_date) if birth_date else None
    assert customer.birth_date == expected


async def test_create_without_birth_date_field_succeeds(client: AsyncClient, db_session: AsyncSession, auth_headers):
    response = await client.post(
        CUSTOMERS_URL,
        headers=auth_headers,
        json={"full_name": "Тест Клиент", "phone": "+79001110003"},
    )
    assert 200 <= response.status_code < 300, response.text
    assert response.json()["birth_date"] is None


# ------------------------------------------------------------------
# Обновление клиента: PATCH /api/v1/customers/{id}
# ------------------------------------------------------------------


@pytest.mark.parametrize("birth_date", INVALID_BIRTH_DATES)
async def test_update_invalid_birth_date_returns_422(
    client: AsyncClient, db_session: AsyncSession, auth_headers, birth_date
):
    customer = await _insert_customer(db_session, birth_date=date(1990, 5, 1))
    response = await client.patch(
        f"{CUSTOMERS_URL}/{customer.id}",
        headers=auth_headers,
        json={"birth_date": birth_date},
    )
    _assert_birth_date_422(response)


@pytest.mark.parametrize("birth_date", VALID_BIRTH_DATES)
async def test_update_valid_birth_date_is_saved(
    client: AsyncClient, db_session: AsyncSession, auth_headers, birth_date
):
    customer = await _insert_customer(db_session, birth_date=date(1985, 3, 3))
    customer_id = customer.id
    response = await client.patch(
        f"{CUSTOMERS_URL}/{customer_id}",
        headers=auth_headers,
        json={"birth_date": birth_date},
    )
    assert response.status_code == 200, response.text
    assert response.json()["birth_date"] == birth_date

    db_session.expire_all()
    stored = (await db_session.execute(select(Customer).where(Customer.id == customer_id))).scalar_one()
    expected = date.fromisoformat(birth_date) if birth_date else None
    assert stored.birth_date == expected


# ------------------------------------------------------------------
# Старые некорректные данные в БД (вставка напрямую через db_session)
# ------------------------------------------------------------------


async def test_get_customer_with_legacy_birth_date_returns_200(
    client: AsyncClient, db_session: AsyncSession, auth_headers
):
    customer = await _insert_customer(db_session, birth_date=date(1299, 11, 21))
    customer_id = customer.id
    # Сбрасываем identity map, чтобы чтение шло из БД
    db_session.expire_all()

    response = await client.get(f"{CUSTOMERS_URL}/{customer_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["birth_date"] == "1299-11-21"


async def test_list_customers_with_legacy_birth_date_returns_200(
    client: AsyncClient, db_session: AsyncSession, auth_headers
):
    customer = await _insert_customer(db_session, birth_date=date(1299, 11, 21))
    customer_id = str(customer.id)
    db_session.expire_all()

    response = await client.get(CUSTOMERS_URL, headers=auth_headers)
    assert response.status_code == 200, response.text
    items = {item["id"]: item for item in response.json()["items"]}
    assert customer_id in items
    assert items[customer_id]["birth_date"] == "1299-11-21"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"full_name": "Петров Пётр Петрович"}, id="full_name"),
        pytest.param({"phone": "+79003334455"}, id="phone"),
    ],
)
async def test_update_other_fields_with_legacy_birth_date_returns_200(
    client: AsyncClient, db_session: AsyncSession, auth_headers, payload
):
    customer = await _insert_customer(db_session, birth_date=date(1299, 11, 21))
    customer_id = customer.id

    response = await client.patch(
        f"{CUSTOMERS_URL}/{customer_id}",
        headers=auth_headers,
        json=payload,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    for field, value in payload.items():
        assert body[field] == value
    # Старая дата не тронута и не блокирует правку
    assert body["birth_date"] == "1299-11-21"

    db_session.expire_all()
    stored = (await db_session.execute(select(Customer).where(Customer.id == customer_id))).scalar_one()
    assert stored.birth_date == date(1299, 11, 21)

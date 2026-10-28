"""Нативные PG ENUM и значения enum-ов: ORM, схема тестовой БД и ответы API (П6).

Проверяется, что:
- значения enum-ов, отличные от значений по умолчанию, пишутся и читаются через ORM;
- в тестовой БД (схема создана из моделей через create_all) enum-колонки имеют нативные
  типы PG с теми же именами, что заданы в models (name="...");
- списки эндпоинтов отдают созданные записи со строковыми значениями статусов.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models import (
    Bike,
    BikeStatus,
    Booking,
    BookingStatus,
    Branch,
    Customer,
    CustomerDocumentType,
    Lead,
    LeadSource,
    LeadSourceType,
    LeadStatus,
    Task,
    TaskPriority,
    TaskStatus,
    TaskType,
    User,
    UserRole,
)

BIKES_URL = "/api/v1/bikes"
LEADS_URL = "/api/v1/leads"
TASKS_URL = "/api/v1/tasks"
CUSTOMERS_URL = "/api/v1/customers"

# Нативные PG ENUM в БД: (таблица, колонка, имя типа)
NATIVE_ENUM_COLUMNS = [
    pytest.param("bike", "status", "bike_status_enum", id="bike.status"),
    pytest.param("booking", "status", "booking_status_enum", id="booking.status"),
    pytest.param("lead", "status", "lead_status_enum", id="lead.status"),
    pytest.param("lead_source", "type", "lead_source_type_enum", id="lead_source.type"),
    pytest.param("task", "status", "task_status_enum", id="task.status"),
    pytest.param("task", "type", "task_type_enum", id="task.type"),
    pytest.param("user", "role", "user_role_enum", id="user.role"),
]


async def _create_enum_records(db: AsyncSession) -> Dict[str, object]:
    """Создать связанные записи с нестандартными значениями enum-ов.

    Booking создаётся: нужны только филиал, байк и клиент, связей с лидом нет.
    """
    branch = Branch(name="Тестовый филиал", address="ул. Тестовая, 1")
    db.add(branch)
    await db.flush()

    bike = Bike(branch_id=branch.id, model="Тестовый байк", status=BikeStatus.MAINTENANCE)
    customer = Customer(full_name="Тестовый клиент")
    db.add_all([bike, customer])
    await db.flush()

    start_at = datetime.now(timezone.utc) + timedelta(days=1)
    booking = Booking(
        branch_id=branch.id,
        bike_id=bike.id,
        customer_id=customer.id,
        start_at=start_at,
        end_at=start_at + timedelta(days=2),
        status=BookingStatus.CONFIRMED,
        price_per_period=1000.0,
        total_price=2000.0,
    )
    source = LeadSource(type=LeadSourceType.TELEGRAM, name="Тестовый источник", config={}, is_active=True)
    db.add_all([booking, source])
    await db.flush()

    lead = Lead(
        source_id=source.id,
        external_id="test-lead-enums",
        status=LeadStatus.WON,
        client_name="Тестовый клиент",
        customer_id=customer.id,
        bike_id=bike.id,
    )
    db.add(lead)
    await db.flush()

    task = Task(
        type=TaskType.CONTRACT,
        title="Тестовая задача с enum-ами",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.HIGH,
        related_lead_id=lead.id,
        related_bike_id=bike.id,
    )
    mechanic = User(
        email="mechanic@test.local",
        hashed_password=get_password_hash("mechanic-password-123"),
        full_name="Тестовый механик",
        role=UserRole.MECHANIC,
        is_active=True,
    )
    db.add_all([task, mechanic])
    await db.commit()

    return {
        "branch": branch,
        "bike": bike,
        "customer": customer,
        "booking": booking,
        "source": source,
        "lead": lead,
        "task": task,
        "mechanic": mechanic,
    }


def _find_by_id(items: List[dict], item_id: str) -> dict:
    """Найти запись в списке ответа по id; если нет, тест падает с понятным сообщением."""
    found: Optional[dict] = next((item for item in items if item["id"] == item_id), None)
    if found is None:
        pytest.fail(f"Запись {item_id} не найдена в ответе списка")
    return found


async def test_enum_values_roundtrip_through_orm(db_session: AsyncSession):
    """Нестандартные значения enum-ов записываются, читаются обратно и совпадают в БД."""
    rec = await _create_enum_records(db_session)
    # id читаем до expire_all: иначе доступ к атрибуту уйдёт в ленивую загрузку вне async-контекста
    ids = {key: obj.id for key, obj in rec.items()}
    db_session.expire_all()

    bike = (await db_session.execute(select(Bike).where(Bike.id == ids["bike"]))).scalar_one()
    booking = (await db_session.execute(select(Booking).where(Booking.id == ids["booking"]))).scalar_one()
    source = (await db_session.execute(select(LeadSource).where(LeadSource.id == ids["source"]))).scalar_one()
    lead = (await db_session.execute(select(Lead).where(Lead.id == ids["lead"]))).scalar_one()
    task = (await db_session.execute(select(Task).where(Task.id == ids["task"]))).scalar_one()
    mechanic = (await db_session.execute(select(User).where(User.id == ids["mechanic"]))).scalar_one()

    assert bike.status == BikeStatus.MAINTENANCE
    assert booking.status == BookingStatus.CONFIRMED
    assert source.type == LeadSourceType.TELEGRAM
    assert lead.status == LeadStatus.WON
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.type == TaskType.CONTRACT
    assert task.priority == TaskPriority.HIGH
    assert mechanic.role == UserRole.MECHANIC

    # Сырые строки в БД: значения PG ENUM совпадают с value из Python-enum
    raw_checks = [
        ("select status::text from bike where id = :id", {"id": ids["bike"]}, "maintenance"),
        ("select status::text from booking where id = :id", {"id": ids["booking"]}, "confirmed"),
        ("select type::text from lead_source where id = :id", {"id": ids["source"]}, "telegram"),
        ("select status::text from lead where id = :id", {"id": ids["lead"]}, "won"),
        ("select status::text from task where id = :id", {"id": ids["task"]}, "in_progress"),
        ("select type::text from task where id = :id", {"id": ids["task"]}, "contract"),
        ("select role::text from \"user\" where id = :id", {"id": ids["mechanic"]}, "mechanic"),
    ]
    for sql, params, expected in raw_checks:
        value = (await db_session.execute(text(sql), params)).scalar_one()
        assert value == expected, f"{sql}: в БД {value!r}, ожидалось {expected!r}"


async def test_bike_status_pg_typeof_is_native_enum(db_session: AsyncSession):
    """В тестовой БД bike.status имеет нативный тип bike_status_enum."""
    await _create_enum_records(db_session)
    result = await db_session.execute(text("select pg_typeof(status)::text from bike limit 1"))
    assert result.scalar_one() == "bike_status_enum"


@pytest.mark.parametrize("table, column, type_name", NATIVE_ENUM_COLUMNS)
async def test_native_enum_column_types_in_test_db(db_session: AsyncSession, table: str, column: str, type_name: str):
    """Все 7 нативных enum-колонок в тестовой БД созданы как USER-DEFINED с нужным именем типа."""
    result = await db_session.execute(
        text(
            "select data_type, udt_name from information_schema.columns "
            "where table_schema = current_schema() and table_name = :table and column_name = :column"
        ),
        {"table": table, "column": column},
    )
    row = result.one()
    assert row.data_type == "USER-DEFINED"
    assert row.udt_name == type_name


async def test_list_endpoints_return_string_enum_values(
    client: AsyncClient, auth_headers: Dict[str, str], db_session: AsyncSession
):
    """GET /bikes, /leads, /tasks, /customers → 200, созданные записи со строковыми статусами."""
    rec = await _create_enum_records(db_session)
    bike_id, lead_id, task_id, customer_id = (str(rec[k].id) for k in ("bike", "lead", "task", "customer"))

    bikes = await client.get(BIKES_URL, headers=auth_headers)
    assert bikes.status_code == 200, bikes.text
    bike_item = _find_by_id(bikes.json()["items"], bike_id)
    assert bike_item["status"] == "maintenance"

    leads = await client.get(LEADS_URL, headers=auth_headers)
    assert leads.status_code == 200, leads.text
    lead_item = _find_by_id(leads.json()["items"], lead_id)
    assert lead_item["status"] == "won"

    tasks = await client.get(TASKS_URL, headers=auth_headers)
    assert tasks.status_code == 200, tasks.text
    task_item = _find_by_id(tasks.json()["items"], task_id)
    assert task_item["status"] == "in_progress"
    assert task_item["type"] == "contract"
    assert task_item["priority"] == "high"

    customers = await client.get(CUSTOMERS_URL, headers=auth_headers)
    assert customers.status_code == 200, customers.text
    customer_item = _find_by_id(customers.json()["items"], customer_id)
    # document_type в БД varchar, в модели native_enum=False: значение строкой по умолчанию
    assert customer_item["document_type"] == CustomerDocumentType.PASSPORT_RF.value

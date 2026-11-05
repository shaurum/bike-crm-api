"""Публичный список байков для сайта: только открытые поля и честная доступность."""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Bike, BikePrice, BikeStatus, Booking, BookingStatus, Branch, Customer

URL = "/api/v1/public/bikes"
SECRET_FIELDS = {"purchase_price", "frame_number", "notes", "tracker_id", "specs", "branch_id", "deleted_at"}


def _headers() -> dict:
    return {"X-API-Key": settings.PUBLIC_API_KEY}


async def _fleet(db: AsyncSession) -> dict:
    branch = Branch(name="Филиал", address="ул. Тестовая, 1")
    db.add(branch)
    await db.flush()
    free = Bike(branch_id=branch.id, model="Maikaline U2", frame_number="MK-1", purchase_price=120000.0,
                notes="закуплен у поставщика", tracker_id=17522, photos=["/uploads/bike-1.webp"])
    rented = Bike(branch_id=branch.id, model="Maikaline U2", frame_number="MK-2")
    repair = Bike(branch_id=branch.id, model="Volt X", status=BikeStatus.MAINTENANCE)
    customer = Customer(full_name="Клиент")
    db.add_all([free, rented, repair, customer])
    await db.flush()
    db.add_all([
        BikePrice(bike_id=free.id, duration_min=30 * 24 * 60, price=20000.0, deposit=5000.0),
        BikePrice(bike_id=free.id, duration_min=7 * 24 * 60, duration_max=14 * 24 * 60 - 1, price=6500.0, deposit=5000.0),
        BikePrice(bike_id=free.id, duration_min=14 * 24 * 60, price=99999.0, is_active=False),
    ])
    start = datetime.now(timezone.utc) - timedelta(days=1)
    db.add(Booking(branch_id=branch.id, bike_id=rented.id, customer_id=customer.id, start_at=start,
                   end_at=start + timedelta(days=7), status=BookingStatus.ACTIVE,
                   price_per_period=6500.0, total_price=6500.0))
    await db.commit()
    return {"free": free, "rented": rented, "repair": repair}


async def test_requires_api_key(client: AsyncClient):
    assert (await client.get(URL)).status_code == 401
    assert (await client.get(URL, headers={"X-API-Key": "wrong"})).status_code == 401


async def test_whole_fleet_without_private_fields(client: AsyncClient, db_session: AsyncSession):
    fleet = await _fleet(db_session)
    body = (await client.get(URL, params={"available_only": "false"}, headers=_headers())).json()
    assert len(body) == 3
    for item in body:
        assert not SECRET_FIELDS & item.keys()
    by_id = {item["id"]: item for item in body}
    assert by_id[str(fleet["free"].id)]["is_available"] is True
    assert by_id[str(fleet["rented"].id)]["is_available"] is False
    assert by_id[str(fleet["repair"].id)]["is_available"] is False
    free = by_id[str(fleet["free"].id)]
    assert free["photos"] == ["/uploads/bike-1.webp"]
    # Неактивные цены не публикуются, остальные — по возрастанию срока
    assert [p["price"] for p in free["prices"]] == [6500.0, 20000.0]


async def test_available_only_by_default(client: AsyncClient, db_session: AsyncSession):
    fleet = await _fleet(db_session)
    body = (await client.get(URL, headers=_headers())).json()
    assert [item["id"] for item in body] == [str(fleet["free"].id)]

    one = (await client.get(f"{URL}/{fleet['rented'].id}", headers=_headers())).json()
    assert one["is_available"] is False and "frame_number" not in one

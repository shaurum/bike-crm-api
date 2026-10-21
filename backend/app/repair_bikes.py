"""Разблокировка байков, оставшихся в резерве или аренде без сделки.

Запуск:  docker compose exec api python -m app.repair_bikes

Исправляет состояние после удаления лидов: байк, к которому больше нет
привязанного лида, возвращается в свободные. Байки на обслуживании не трогаем.
"""

import asyncio

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models import Bike, BikeStatus, Lead


async def repair() -> None:
    async with async_session_maker() as db:
        bikes = (await db.execute(select(Bike).where(Bike.deleted_at.is_(None)))).scalars().all()

        fixed = 0
        for bike in bikes:
            if bike.status == BikeStatus.AVAILABLE:
                continue

            linked = (
                await db.execute(
                    select(Lead.id).where(Lead.bike_id == bike.id, Lead.deleted_at.is_(None)).limit(1)
                )
            ).scalars().first()

            if linked:
                continue

            print(f"  {bike.model} ({bike.status}) -> свободен, сделки нет")
            bike.status = BikeStatus.AVAILABLE
            fixed += 1

        if fixed:
            await db.commit()

    print(f"Готово: освобождено {fixed}")


if __name__ == "__main__":
    asyncio.run(repair())
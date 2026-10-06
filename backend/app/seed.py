"""Начальное наполнение БД: этапы воронки и источники лидов.

Запуск:  docker compose exec api python -m app.seed
Идемпотентно — повторный запуск не создаёт дубли.
"""

import asyncio

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models import LeadSource, LeadSourceType, PipelineStage, Branch, Bike, BikePrice, CompanyProfile

DEFAULT_BRANCH = ("Основной филиал", "Москва, ул. Примерная, 1")

# Демонстрационный байк: показываем, как выглядит карточка гаража
DEMO_BIKE = {
    "model": "Maikaline U2",
    "frame_number": "MK-U2-0001",
    "color": "Чёрный",
    "year": 2025,
    "battery_capacity": 48.0,
    "max_speed": 45,
    "range_km": 80,
    "purchase_price": 120000.0,
    "notes": "Демонстрационный байк. Загрузите фото через карточку.",
    "prices": [
        (7 * 24 * 60, 14 * 24 * 60 - 1, 6500.0),
        (14 * 24 * 60, 30 * 24 * 60 - 1, 12000.0),
        (30 * 24 * 60, None, 20000.0),
    ],
}

PIPELINE_STAGES = [
    ("Новый", 1, "#3B82F6", True, {"task": "Связаться с клиентом"}),
    ("Связались", 2, "#8B5CF6", False, {"task": "Уточнить потребности и бюджет"}),
    ("Договор", 3, "#F59E0B", False, {"task": "Подготовить договор"}),
    ("Оплата", 4, "#10B981", False, {"task": "Принять оплату и залог"}),
    ("Выдан", 5, "#06B6D4", False, {"task": "Выдать байк"}),
    ("Завершён", 6, "#16A34A", False, None),
    ("Отказ", 7, "#EF4444", False, None),
]

LEAD_SOURCES = [
    ("Авито", LeadSourceType.AVITO),
    ("ВКонтакте", LeadSourceType.VK),
    ("Telegram", LeadSourceType.TELEGRAM),
    ("Email", LeadSourceType.EMAIL),
    ("Виджет", LeadSourceType.WIDGET),
    ("Ручной ввод", LeadSourceType.MANUAL),
]


async def seed() -> None:
    async with async_session_maker() as db:
        existing_stages = {
            name for (name,) in (await db.execute(select(PipelineStage.name))).all()
        }
        for name, order, color, is_default, auto_actions in PIPELINE_STAGES:
            if name in existing_stages:
                continue
            db.add(
                PipelineStage(
                    name=name,
                    order=order,
                    color=color,
                    is_default=is_default,
                    auto_actions=auto_actions or {},
                )
            )

        existing_sources = {
            name for (name,) in (await db.execute(select(LeadSource.name))).all()
        }
        for name, source_type in LEAD_SOURCES:
            if name in existing_sources:
                continue
            db.add(LeadSource(name=name, type=source_type, config={}))

        branch = (
            await db.execute(select(Branch).where(Branch.name == DEFAULT_BRANCH[0]))
        ).scalar_one_or_none()
        if not branch:
            branch = Branch(name=DEFAULT_BRANCH[0], address=DEFAULT_BRANCH[1])
            db.add(branch)
            await db.flush()

        demo = (
            await db.execute(
                select(Bike).where(Bike.frame_number == DEMO_BIKE["frame_number"])
            )
        ).scalar_one_or_none()
        if not demo:
            demo = Bike(
                branch_id=branch.id,
                model=DEMO_BIKE["model"],
                frame_number=DEMO_BIKE["frame_number"],
                color=DEMO_BIKE["color"],
                year=DEMO_BIKE["year"],
                battery_capacity=DEMO_BIKE["battery_capacity"],
                max_speed=DEMO_BIKE["max_speed"],
                range_km=DEMO_BIKE["range_km"],
                purchase_price=DEMO_BIKE["purchase_price"],
                notes=DEMO_BIKE["notes"],
            )
            db.add(demo)
            await db.flush()
            for duration_min, duration_max, price in DEMO_BIKE["prices"]:
                db.add(
                    BikePrice(
                        bike_id=demo.id,
                        duration_min=duration_min,
                        duration_max=duration_max,
                        price=price,
                        deposit=0,
                    )
                )

        # Реквизиты арендодателя для договоров
        company = (
            await db.execute(select(CompanyProfile).limit(1))
        ).scalars().first()
        if not company:
            db.add(
                CompanyProfile(
                    name="ИП Леончук Анна Владимировна",
                    address="Москва",
                )
            )

        await db.commit()

    print("Готово: этапы воронки и источники лидов")


if __name__ == "__main__":
    asyncio.run(seed())
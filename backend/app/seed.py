"""Начальное наполнение БД: этапы воронки и источники лидов.

Запуск:  docker compose exec api python -m app.seed
Идемпотентно — повторный запуск не создаёт дубли.
"""

import asyncio

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models import LeadSource, LeadSourceType, PipelineStage

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

        await db.commit()

    print("Готово: этапы воронки и источники лидов")


if __name__ == "__main__":
    asyncio.run(seed())
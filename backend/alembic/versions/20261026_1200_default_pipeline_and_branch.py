"""Базовые данные: филиал и этапы воронки.

На боевой базе не были созданы этапы воронки и филиал: воронка пустая,
а при добавлении байка форма отвечает «В системе нет филиала».
Миграция добавляет их, только если записей ещё нет, поэтому безопасна
для баз с данными. Демо-байк не создаём.
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "20261026_1200"
down_revision = "20261021_1600"
branch_labels = None
depends_on = None

# Совпадает с app/seed.py: (название, порядок, цвет, по умолчанию, авто-действия)
PIPELINE_STAGES = [
    ("Новый", 1, "#3B82F6", True, {"task": "Связаться с клиентом"}),
    ("Связались", 2, "#8B5CF6", False, {"task": "Уточнить потребности и бюджет"}),
    ("Договор", 3, "#F59E0B", False, {"task": "Подготовить договор"}),
    ("Оплата", 4, "#10B981", False, {"task": "Принять оплату и залог"}),
    ("Выдан", 5, "#06B6D4", False, {"task": "Выдать байк"}),
    ("Завершён", 6, "#16A34A", False, None),
    ("Отказ", 7, "#EF4444", False, None),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Адрес оставляем пустым: его заполняют в настройках филиала
    conn.execute(
        sa.text(
            "INSERT INTO branch (id, name, address, timezone, is_active, created_at, updated_at) "
            "SELECT gen_random_uuid(), 'Основной филиал', '', 'Europe/Moscow', true, now(), now() "
            "WHERE NOT EXISTS (SELECT 1 FROM branch)"
        )
    )

    for name, sort_order, color, is_default, auto_actions in PIPELINE_STAGES:
        conn.execute(
            sa.text(
                'INSERT INTO pipeline_stage (id, name, "order", color, is_default, auto_actions, created_at, updated_at) '
                "SELECT gen_random_uuid(), CAST(:name AS varchar(100)), CAST(:sort_order AS integer), "
                "CAST(:color AS varchar(7)), "
                "CAST(:is_default AS boolean) AND NOT EXISTS (SELECT 1 FROM pipeline_stage WHERE is_default), "
                "CAST(:auto_actions AS jsonb), now(), now() "
                "WHERE NOT EXISTS (SELECT 1 FROM pipeline_stage WHERE name = :name)"
            ),
            {
                "name": name,
                "sort_order": sort_order,
                "color": color,
                "is_default": is_default,
                "auto_actions": json.dumps(auto_actions or {}),
            },
        )


def downgrade() -> None:
    # Данные пользователя не удаляем: откат не должен трогать воронку и филиал
    pass

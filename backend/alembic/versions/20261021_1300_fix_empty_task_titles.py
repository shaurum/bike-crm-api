"""Починка задач с пустым названием.

В БД попали строки title='  ' — валидатор схемы ронял ответ всего списка
задач (ResponseValidationError). Названия без текста заменяем на заглушку,
валидатор переезжает на схему записи (см. TaskCreate).
"""

import sqlalchemy as sa
from alembic import op

revision = "20261021_1300"
down_revision = "20261008_1600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE task SET title = 'Задача без названия' "
            "WHERE btrim(coalesce(title, '')) = ''"
        )
    )


def downgrade() -> None:
    pass

"""Мягкое удаление: карточки клиентов и лиды скрываются, но не теряются.

Статистика, переписка, документы и история аренд остаются нетронутыми —
строки живут в БД, скрытие фильтруется через deleted_at.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261008_1600"
down_revision = "70f2d3b757d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customer",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Дата мягкого удаления",
        ),
    )
    op.add_column(
        "lead",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Дата мягкого удаления",
        ),
    )


def downgrade() -> None:
    op.drop_column("lead", "deleted_at")
    op.drop_column("customer", "deleted_at")

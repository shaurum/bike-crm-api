"""lead_message: добавить недостающую колонку updated_at

Модель LeadMessage наследует TimestampMixin, но в начальной миграции
колонка updated_at не была создана — SELECT по связи падал с
UndefinedColumnError.

Revision ID: 20261005_120000
Revises: 001
"""

import sqlalchemy as sa
from alembic import op

revision = "20261005_120000"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lead_message",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("lead_message", "updated_at")
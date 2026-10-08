"""Чат можно скрыть из ленты: архив вместо удаления.

Скрытый чат остаётся с историей, но не появляется в списке, а новые
входящие не увеличивают счётчик непрочитанных — так почтовый спам
перестаёт сыпаться в ленту.

Revision ID: 20261007_110000
Revises: 20261007_100000
"""

import sqlalchemy as sa
from alembic import op

revision = "20261007_110000"
down_revision = "20261007_100000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation",
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Скрыт из ленты; входящие не поднимают счётчик",
        ),
    )


def downgrade() -> None:
    op.drop_column("conversation", "is_archived")

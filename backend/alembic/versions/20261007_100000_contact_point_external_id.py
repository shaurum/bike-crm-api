"""Внешний идентификатор контакта (chat_id в Авито).

Чтобы ответить в мессенджер Авито, нужен chat_id конкретного диалога.
Он приходит во входящем вебхуке и сохраняется в contact_point.external_id.

Revision ID: 20261007_100000
Revises: 20261006_170000
"""

import sqlalchemy as sa
from alembic import op

revision = "20261007_100000"
down_revision = "20261006_170000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contact_point",
        sa.Column("external_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_contact_point_external_id",
        "contact_point",
        ["external_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_contact_point_external_id", table_name="contact_point")
    op.drop_column("contact_point", "external_id")

"""Предзаписанные сообщения: готовые ответы клиентам."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20261021_1600"
down_revision = "20261021_1500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canned_reply",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            comment="Уникальный идентификатор",
        ),
        sa.Column("title", sa.String(200), nullable=False, comment="Название для списка"),
        sa.Column("text", sa.Text(), nullable=False, comment="Текст сообщения"),
        sa.Column(
            "shortcut",
            sa.String(50),
            nullable=True,
            comment="Быстрая команда, напр. /привет",
        ),
        sa.Column(
            "created_by_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
            comment="Автор",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Дата создания",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Дата обновления",
        ),
    )
    op.create_index("ix_canned_reply_shortcut", "canned_reply", ["shortcut"])


def downgrade() -> None:
    op.drop_index("ix_canned_reply_shortcut", table_name="canned_reply")
    op.drop_table("canned_reply")

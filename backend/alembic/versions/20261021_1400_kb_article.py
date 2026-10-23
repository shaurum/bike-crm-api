"""Библиотека знаний: таблица статей."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20261021_1400"
down_revision = "20261021_1300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_article",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            comment="Уникальный идентификатор",
        ),
        sa.Column("title", sa.String(300), nullable=False, comment="Заголовок"),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="Текст статьи",
        ),
        sa.Column(
            "category",
            sa.String(100),
            nullable=True,
            comment="Раздел/категория",
        ),
        sa.Column(
            "is_pinned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Закреплена сверху",
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
    op.create_index("ix_kb_article_category", "kb_article", ["category"])


def downgrade() -> None:
    op.drop_index("ix_kb_article_category", table_name="kb_article")
    op.drop_table("kb_article")

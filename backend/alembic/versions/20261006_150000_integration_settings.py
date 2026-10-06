"""Настройки интеграций в базе

Позволяет править подключения из интерфейса, а не через .env.
Секреты хранятся отдельно и никогда не возвращаются в API.

Revision ID: 20261006_150000
Revises: 20261006_140000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20261006_150000"
down_revision = "20261006_140000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_setting",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "name",
            sa.String(50),
            nullable=False,
            unique=True,
            comment="Ключ интеграции: email, telegram, avito, vk, widget",
        ),
        sa.Column("title", sa.String(100), nullable=False, comment="Название в интерфейсе"),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "config",
            sa.JSON(),
            nullable=False,
            server_default="{}",
            comment="Обычные настройки",
        ),
        sa.Column(
            "secret",
            sa.JSON(),
            nullable=False,
            server_default="{}",
            comment="Секреты: пароли, токены, ключи",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_integration_setting_name", "integration_setting", ["name"], unique=True
    )

    # Стартовые записи интеграций
    op.execute(
        """
        INSERT INTO integration_setting (id, name, title, is_enabled, config, secret)
        VALUES
          (gen_random_uuid(), 'email', 'Электронная почта', false,
           '{"provider": "smtp", "host": "", "port": 587, "username": "",
             "from_email": "", "from_name": "", "use_tls": true}'::json, '{}'::json),
          (gen_random_uuid(), 'telegram', 'Telegram', false, '{}'::json, '{}'::json),
          (gen_random_uuid(), 'avito', 'Авито', false, '{}'::json, '{}'::json),
          (gen_random_uuid(), 'vk', 'ВКонтакте', false, '{}'::json, '{}'::json),
          (gen_random_uuid(), 'widget', 'Виджет на сайте', false, '{}'::json, '{}'::json)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_integration_setting_name", table_name="integration_setting")
    op.drop_table("integration_setting")
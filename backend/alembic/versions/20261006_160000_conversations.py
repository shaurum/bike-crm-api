"""Диалоги и контактные точки клиента.

Чат живёт отдельно от сделки: у клиента один диалог, сообщения в нём
помечены каналом (email, telegram, whatsapp), а способы связи хранятся
в contact_point - их может быть несколько.

Revision ID: 20261006_160000
Revises: 20261006_150000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20261006_160000"
down_revision = "20261006_150000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Телефон больше не обязателен: клиент может прийти только из письма
    op.alter_column(
        "customer", "phone", existing_type=sa.String(length=50), nullable=True
    )

    # Способы связи одного клиента: почта, телеграм, вотсап и т.д.
    op.create_table(
        "contact_point",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "customer_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("customer.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
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
        sa.UniqueConstraint("customer_id", "channel", "value", name="uq_contact_point_value"),
    )
    op.create_index(
        "ix_contact_point_channel_value", "contact_point", ["channel", "value"]
    )

    # Один диалог на клиента. lead_id - контекст сделки, он не обязателен:
    # чат переживает завершение сделки.
    op.create_table(
        "conversation",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "customer_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("customer.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lead_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("lead.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="open",
            comment="open / closed",
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unread_count", sa.Integer, nullable=False, server_default="0"),
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
        sa.UniqueConstraint("customer_id", name="uq_conversation_customer"),
    )
    op.create_index(
        "ix_conversation_last_message", "conversation", ["last_message_at"]
    )

    # Сообщения переезжают из лида в диалог
    op.add_column(
        "lead_message",
        sa.Column(
            "conversation_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "lead_message",
        sa.Column(
            "author_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "lead_message",
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="false"),
    )
    # Лид больше не обязателен: переписка может быть и без сделки
    op.alter_column(
        "lead_message", "lead_id", existing_type=PG_UUID(as_uuid=True), nullable=True
    )

    # Защита от повторной обработки одного и того же письма
    op.create_index(
        "uq_lead_message_external_unique",
        "lead_message",
        ["channel", "external_msg_id"],
        unique=True,
        postgresql_where=sa.text("external_msg_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE lead_message lm
        SET lead_id = c.lead_id
        FROM conversation c
        WHERE lm.conversation_id = c.id
        """
    )
    op.drop_index("uq_lead_message_external_unique", table_name="lead_message")
    op.drop_column("lead_message", "is_read")
    op.drop_column("lead_message", "author_id")
    op.drop_column("lead_message", "conversation_id")
    op.alter_column(
        "lead_message", "lead_id", existing_type=PG_UUID(as_uuid=True), nullable=False
    )
    op.drop_index("ix_conversation_last_message", table_name="conversation")
    op.drop_table("conversation")
    op.drop_index("ix_contact_point_channel_value", table_name="contact_point")
    op.drop_table("contact_point")
    op.alter_column(
        "customer", "phone", existing_type=sa.String(length=50), nullable=False
    )

"""Хранилище документов и реквизиты арендодателя

- document: сгенерированные PDF и загруженные подписанные сканы
- company_profile: реквизиты ИП/ООО для подстановки в договор

Revision ID: 20261006_130000
Revises: 20261006_120000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20261006_130000"
down_revision = "20261006_120000"
branch_labels = None
depends_on = None

KIND_VALUES = "'contract_rental', 'act_handover', 'act_return', 'memo', 'scan', 'other'"
STATUS_VALUES = "'draft', 'issued', 'signed', 'cancelled'"


def upgrade() -> None:
    op.create_table(
        "document",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("customer.id", ondelete="CASCADE"),
            nullable=True,
            comment="Клиент",
        ),
        sa.Column(
            "lead_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("lead.id", ondelete="SET NULL"),
            nullable=True,
            comment="Сделка, из которой сформирован документ",
        ),
        sa.Column(
            "bike_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("bike.id", ondelete="SET NULL"),
            nullable=True,
            comment="Байк",
        ),
        sa.Column(
            "kind", sa.String(40), nullable=False, server_default="contract_rental",
            comment="Тип документа",
        ),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="draft",
            comment="Статус: черновик, выдан, подписан, отменён",
        ),
        sa.Column("number", sa.String(50), nullable=True, comment="Номер документа"),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Дата выдачи документа",
        ),
        sa.Column("file_url", sa.String(500), nullable=True, comment="Файл PDF или скана"),
        sa.Column("original_name", sa.String(255), nullable=True),
        sa.Column("size", sa.Integer, nullable=True),
        sa.Column(
            "payload",
            sa.JSON(),
            nullable=False,
            server_default="{}",
            comment="Данные документа на момент формирования",
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
        sa.CheckConstraint(f"kind IN ({KIND_VALUES})", name="ck_document_kind"),
        sa.CheckConstraint(f"status IN ({STATUS_VALUES})", name="ck_document_status"),
    )
    op.create_index("ix_document_customer", "document", ["customer_id"])
    op.create_index("ix_document_lead", "document", ["lead_id"])
    op.create_index("ix_document_status", "document", ["status"])
    op.create_index("ix_document_kind", "document", ["kind"])

    op.create_table(
        "company_profile",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, comment="Название или ФИО ИП"),
        sa.Column("ogrnip", sa.String(20), nullable=True, comment="ОГРНИП или ОГРН"),
        sa.Column("inn", sa.String(20), nullable=True, comment="ИНН"),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column(
            "return_address",
            sa.String(500),
            nullable=True,
            comment="Адрес возврата имущества",
        ),
        sa.Column(
            "age_restriction",
            sa.String(50),
            nullable=True,
            comment="Возрастное ограничение для аренды",
        ),
        sa.Column(
            "deposit_return",
            sa.String(500),
            nullable=True,
            comment="Порядок возврата залога",
        ),
        sa.Column(
            "photo_consent",
            sa.String(500),
            nullable=True,
            comment="Условие согласия на фото/видео",
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


def downgrade() -> None:
    op.drop_table("company_profile")
    op.drop_index("ix_document_kind", table_name="document")
    op.drop_index("ix_document_status", table_name="document")
    op.drop_index("ix_document_lead", table_name="document")
    op.drop_index("ix_document_customer", table_name="document")
    op.drop_table("document")
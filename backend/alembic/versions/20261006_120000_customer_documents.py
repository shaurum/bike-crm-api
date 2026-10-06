"""Паспортные данные клиента и сканы документов

- customer: дата рождения, место рождения, страна, код подразделения,
  тип документа удостоверения личности
- новая таблица customer_document для сканов

Тип документа хранится строкой с CHECK-ограничением, как и остальные
перечисления в проекте (native_enum=False), чтобы не плодить типы в Postgres.

Revision ID: 20261006_120000
Revises: 20261005_160000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20261006_120000"
down_revision = "20261005_160000"
branch_labels = None
depends_on = None

DOCUMENT_TYPES = (
    "'passport_rf', 'foreign_passport', 'residence_permit', "
    "'id_card', 'driver_license', 'other'"
)
CHECK_SQL = f"document_type IN ({DOCUMENT_TYPES})"
KIND_CHECK_SQL = f"kind IN ({DOCUMENT_TYPES})"


def upgrade() -> None:
    op.add_column(
        "customer",
        sa.Column(
            "document_type",
            sa.String(30),
            nullable=False,
            server_default="passport_rf",
            comment="Тип документа, удостоверяющего личность",
        ),
    )
    op.add_column(
        "customer",
        sa.Column(
            "country",
            sa.String(100),
            nullable=False,
            server_default="Россия",
            comment="Гражданство или страна документа",
        ),
    )
    op.add_column(
        "customer",
        sa.Column("birth_date", sa.Date, nullable=True, comment="Дата рождения"),
    )
    op.add_column(
        "customer",
        sa.Column("birth_place", sa.String(255), nullable=True, comment="Место рождения"),
    )
    op.add_column(
        "customer",
        sa.Column(
            "passport_code",
            sa.String(20),
            nullable=True,
            comment="Код подразделения паспорта",
        ),
    )
    op.create_check_constraint(
        "ck_customer_document_type", "customer", CHECK_SQL
    )

    op.create_table(
        "customer_document",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("customer.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.String(30),
            nullable=False,
            server_default="passport_rf",
            comment="Что за документ: паспорт, права и т.д.",
        ),
        sa.Column("file_url", sa.String(500), nullable=False, comment="Путь к файлу"),
        sa.Column("original_name", sa.String(255), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("size", sa.Integer, nullable=True, comment="Размер в байтах"),
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
        sa.CheckConstraint(KIND_CHECK_SQL, name="ck_customer_document_kind"),
    )
    op.create_index("ix_customer_document_customer", "customer_document", ["customer_id"])
    op.create_index("ix_customer_birth_date", "customer", ["birth_date"])


def downgrade() -> None:
    op.drop_index("ix_customer_birth_date", table_name="customer")
    op.drop_index("ix_customer_document_customer", table_name="customer_document")
    op.drop_table("customer_document")
    op.drop_constraint("ck_customer_document_type", "customer", type_="check")
    op.drop_column("customer", "passport_code")
    op.drop_column("customer", "birth_place")
    op.drop_column("customer", "birth_date")
    op.drop_column("customer", "country")
    op.drop_column("customer", "document_type")
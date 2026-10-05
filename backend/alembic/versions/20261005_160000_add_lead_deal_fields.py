"""Поля сделки на карточке лида + комментарии менеджеров

- lead: customer_id, bike_id, amount, deal_due_at, rental_start_at, rental_end_at
- новая таблица lead_comment

Revision ID: 20261005_160000
Revises: 20261005_120000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20261005_160000"
down_revision = "20261005_120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lead",
        sa.Column("customer_id", PG_UUID(as_uuid=True), sa.ForeignKey("customer.id", ondelete="SET NULL"), nullable=True, comment="Привязанный клиент"),
    )
    op.add_column(
        "lead",
        sa.Column("bike_id", PG_UUID(as_uuid=True), sa.ForeignKey("bike.id", ondelete="SET NULL"), nullable=True, comment="Выбранный байк"),
    )
    op.add_column(
        "lead",
        sa.Column("amount", sa.Numeric(12, 2), nullable=True, comment="Сумма по сделке"),
    )
    op.add_column(
        "lead",
        sa.Column("deal_due_at", sa.DateTime(timezone=True), nullable=True, comment="Срок появления сделки"),
    )
    op.add_column(
        "lead",
        sa.Column("rental_start_at", sa.DateTime(timezone=True), nullable=True, comment="Начало аренды"),
    )
    op.add_column(
        "lead",
        sa.Column("rental_end_at", sa.DateTime(timezone=True), nullable=True, comment="Окончание аренды"),
    )

    op.create_table(
        "lead_comment",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("lead_id", PG_UUID(as_uuid=True), sa.ForeignKey("lead.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", PG_UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_lead_comment_lead_created", "lead_comment", ["lead_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_lead_comment_lead_created", table_name="lead_comment")
    op.drop_table("lead_comment")
    op.drop_column("lead", "rental_end_at")
    op.drop_column("lead", "rental_start_at")
    op.drop_column("lead", "deal_due_at")
    op.drop_column("lead", "amount")
    op.drop_column("lead", "bike_id")
    op.drop_column("lead", "customer_id")
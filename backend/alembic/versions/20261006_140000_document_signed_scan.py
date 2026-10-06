"""Подписанный скан прикладывается к документу

Document: signed_file_url, signed_original_name, signed_at

Revision ID: 20261006_140000
Revises: 20261006_130000
"""

import sqlalchemy as sa
from alembic import op

revision = "20261006_140000"
down_revision = "20261006_130000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column(
            "signed_file_url",
            sa.String(500),
            nullable=True,
            comment="Подписанный скан, приложенный к документу",
        ),
    )
    op.add_column(
        "document",
        sa.Column("signed_original_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "document",
        sa.Column(
            "signed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Когда приложен подписанный скан",
        ),
    )
    op.add_column(
        "document",
        sa.Column(
            "signed_size", sa.Integer, nullable=True, comment="Размер скана в байтах"
        ),
    )


def downgrade() -> None:
    op.drop_column("document", "signed_size")
    op.drop_column("document", "signed_at")
    op.drop_column("document", "signed_original_name")
    op.drop_column("document", "signed_file_url")
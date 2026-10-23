"""Вложения в сообщениях чатов."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261021_1500"
down_revision = "20261021_1400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lead_message",
        sa.Column(
            "attachments",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'"),
            comment="Вложения: [{url, name, content_type}]",
        ),
    )


def downgrade() -> None:
    op.drop_column("lead_message", "attachments")

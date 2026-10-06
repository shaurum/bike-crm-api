"""Сообщения чата переживают удаление сделки.

Раньше lead_message.lead_id был ON DELETE CASCADE: удалили лид — пропала
вся переписка, хотя чат должен жить отдельно от сделки.

Revision ID: 20261006_170000
Revises: 20261006_160000
"""

from alembic import op

revision = "20261006_170000"
down_revision = "20261006_160000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("lead_message_lead_id_fkey", "lead_message", type_="foreignkey")
    op.create_foreign_key(
        "lead_message_lead_id_fkey",
        "lead_message",
        "lead",
        ["lead_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("lead_message_lead_id_fkey", "lead_message", type_="foreignkey")
    op.create_foreign_key(
        "lead_message_lead_id_fkey",
        "lead_message",
        "lead",
        ["lead_id"],
        ["id"],
        ondelete="CASCADE",
    )
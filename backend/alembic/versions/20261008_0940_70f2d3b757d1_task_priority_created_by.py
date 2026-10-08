"""task priority created_by

Revision ID: 70f2d3b757d1
Revises: d1e16c8c9514
Create Date: 2026-10-08 09:40:33.658517

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '70f2d3b757d1'
down_revision: Union[str, None] = 'd1e16c8c9514'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task",
        sa.Column(
            "priority",
            sa.String(10),
            nullable=False,
            server_default="normal",
        ),
    )
    op.add_column(
        "task",
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_constraint("task_created_by_id_fkey", "task", type_="foreignkey")
    op.drop_column("task", "created_by_id")
    op.drop_column("task", "priority")

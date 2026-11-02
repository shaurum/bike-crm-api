"""bike tracker id

Revision ID: 20261102_1200
Revises: 20261027_1200
Create Date: 2026-11-02 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20261102_1200'
down_revision: Union[str, None] = '20261027_1200'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'bike',
        sa.Column('tracker_id', sa.Integer(), nullable=True, comment='ID трекера в GDEGAZEL'),
    )
    op.create_index('ix_bike_tracker_id', 'bike', ['tracker_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_bike_tracker_id', table_name='bike')
    op.drop_column('bike', 'tracker_id')

"""add retry_count and last_error to file_metadata

Revision ID: 9b3c2a10d4e5
Revises: 8f2a1b90c3d4
Create Date: 2026-08-29 16:48:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b3c2a10d4e5'
down_revision: Union[str, None] = '8f2a1b90c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'file_metadata',
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0')
    )
    op.add_column(
        'file_metadata',
        sa.Column('last_error', sa.String(length=500), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('file_metadata', 'last_error')
    op.drop_column('file_metadata', 'retry_count')

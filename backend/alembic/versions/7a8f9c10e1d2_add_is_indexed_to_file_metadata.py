"""add_is_indexed_to_file_metadata

Revision ID: 7a8f9c10e1d2
Revises: ce06d2ee9755
Create Date: 2026-08-29 12:38:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a8f9c10e1d2'
down_revision: Union[str, Sequence[str], None] = 'ce06d2ee9755'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by adding is_indexed column to file_metadata."""
    op.add_column('file_metadata', sa.Column('is_indexed', sa.Boolean(), server_default=sa.text('0'), nullable=False))


def downgrade() -> None:
    """Downgrade schema by dropping is_indexed column from file_metadata."""
    op.drop_column('file_metadata', 'is_indexed')

"""add indexing_status and index_version to file_metadata

Revision ID: 8f2a1b90c3d4
Revises: 7a8f9c10e1d2
Create Date: 2026-08-29 15:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f2a1b90c3d4'
down_revision: Union[str, None] = '7a8f9c10e1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'file_metadata',
        sa.Column('indexing_status', sa.String(length=20), nullable=False, server_default='pending')
    )
    op.add_column(
        'file_metadata',
        sa.Column('index_version', sa.Integer(), nullable=False, server_default='1')
    )
    # Alter tags column to VARCHAR(50) for strict 50-character limit
    op.alter_column(
        'file_metadata',
        'tags',
        existing_type=sa.String(length=100),
        type_=sa.String(length=50),
        existing_nullable=True
    )


def downgrade() -> None:
    op.drop_column('file_metadata', 'index_version')
    op.drop_column('file_metadata', 'indexing_status')
    op.alter_column(
        'file_metadata',
        'tags',
        existing_type=sa.String(length=50),
        type_=sa.String(length=100),
        existing_nullable=True
    )

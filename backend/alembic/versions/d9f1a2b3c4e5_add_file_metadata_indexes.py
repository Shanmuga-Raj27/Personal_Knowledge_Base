"""add file metadata indexes

Revision ID: d9f1a2b3c4e5
Revises: ce06d2ee9755
Create Date: 2026-08-30 19:05:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd9f1a2b3c4e5'
down_revision = '9b3c2a10d4e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create single-column indexes on file_metadata
    op.create_index('ix_file_metadata_status', 'file_metadata', ['status'], unique=False)
    op.create_index('ix_file_metadata_is_indexed', 'file_metadata', ['is_indexed'], unique=False)
    op.create_index('ix_file_metadata_indexing_status', 'file_metadata', ['indexing_status'], unique=False)
    op.create_index('ix_file_metadata_userid', 'file_metadata', ['userid'], unique=False)

    # Create composite indexes on file_metadata
    op.create_index('idx_user_status', 'file_metadata', ['userid', 'status'], unique=False)
    op.create_index('idx_indexing_recovery', 'file_metadata', ['status', 'is_indexed', 'indexing_status'], unique=False)


def downgrade() -> None:
    # Drop composite indexes
    op.drop_index('idx_indexing_recovery', table_name='file_metadata')
    op.drop_index('idx_user_status', table_name='file_metadata')

    # Drop single-column indexes
    op.drop_index('ix_file_metadata_userid', table_name='file_metadata')
    op.drop_index('ix_file_metadata_indexing_status', table_name='file_metadata')
    op.drop_index('ix_file_metadata_is_indexed', table_name='file_metadata')
    op.drop_index('ix_file_metadata_status', table_name='file_metadata')

"""daily reading cache

Revision ID: b7f3a1c9d2e4
Revises: 9633e83a6553
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7f3a1c9d2e4'
down_revision: Union[str, Sequence[str], None] = '9633e83a6553'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('daily_reading_cache',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('reading_date', sa.Date(), nullable=False),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('birth_profile_version', sa.Integer(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'reading_date', 'language', 'birth_profile_version')
    )
    op.create_index(op.f('ix_daily_reading_cache_user_id'), 'daily_reading_cache', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_daily_reading_cache_user_id'), table_name='daily_reading_cache')
    op.drop_table('daily_reading_cache')

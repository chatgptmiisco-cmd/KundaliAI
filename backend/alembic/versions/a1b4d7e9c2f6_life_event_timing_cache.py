"""life event timing cache (career/wealth/children/foreign travel)

Revision ID: a1b4d7e9c2f6
Revises: f6a9c3e2b8d5
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b4d7e9c2f6'
down_revision: Union[str, Sequence[str], None] = 'f6a9c3e2b8d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('life_event_timing_cache',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('event_type', sa.String(length=32), nullable=False),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('birth_profile_version', sa.Integer(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'event_type', 'language', 'birth_profile_version')
    )
    op.create_index(op.f('ix_life_event_timing_cache_user_id'), 'life_event_timing_cache', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_life_event_timing_cache_user_id'), table_name='life_event_timing_cache')
    op.drop_table('life_event_timing_cache')

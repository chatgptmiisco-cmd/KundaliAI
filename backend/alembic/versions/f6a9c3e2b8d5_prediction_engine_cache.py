"""prediction engine cache (year outlook + marriage timing)

Revision ID: f6a9c3e2b8d5
Revises: e5f7a3b2c9d1
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a9c3e2b8d5'
down_revision: Union[str, Sequence[str], None] = 'e5f7a3b2c9d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('year_outlook_cache',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('birth_profile_version', sa.Integer(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'year', 'language', 'birth_profile_version')
    )
    op.create_index(op.f('ix_year_outlook_cache_user_id'), 'year_outlook_cache', ['user_id'], unique=False)

    op.create_table('marriage_timing_cache',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('birth_profile_version', sa.Integer(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'language', 'birth_profile_version')
    )
    op.create_index(op.f('ix_marriage_timing_cache_user_id'), 'marriage_timing_cache', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_marriage_timing_cache_user_id'), table_name='marriage_timing_cache')
    op.drop_table('marriage_timing_cache')
    op.drop_index(op.f('ix_year_outlook_cache_user_id'), table_name='year_outlook_cache')
    op.drop_table('year_outlook_cache')

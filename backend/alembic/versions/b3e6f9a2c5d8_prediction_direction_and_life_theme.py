"""prediction direction column + life theme cache

Revision ID: b3e6f9a2c5d8
Revises: a1b4d7e9c2f6
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3e6f9a2c5d8'
down_revision: Union[str, Sequence[str], None] = 'a1b4d7e9c2f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'marriage_timing_cache',
        sa.Column('direction', sa.String(length=8), nullable=False, server_default='future'),
    )
    op.drop_constraint('marriage_timing_cache_user_id_language_birth_profile_version_key', 'marriage_timing_cache', type_='unique')
    op.create_unique_constraint(
        'marriage_timing_cache_user_id_direction_language_birth_profile_version_key',
        'marriage_timing_cache', ['user_id', 'direction', 'language', 'birth_profile_version'],
    )

    op.add_column(
        'life_event_timing_cache',
        sa.Column('direction', sa.String(length=8), nullable=False, server_default='future'),
    )
    op.drop_constraint('life_event_timing_cache_user_id_event_type_language_birth_profile_version_key', 'life_event_timing_cache', type_='unique')
    op.create_unique_constraint(
        'life_event_timing_cache_user_id_event_type_direction_language_birth_profile_version_key',
        'life_event_timing_cache', ['user_id', 'event_type', 'direction', 'language', 'birth_profile_version'],
    )

    op.create_table('life_theme_cache',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('target_date', sa.Date(), nullable=False),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('birth_profile_version', sa.Integer(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'target_date', 'language', 'birth_profile_version')
    )
    op.create_index(op.f('ix_life_theme_cache_user_id'), 'life_theme_cache', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_life_theme_cache_user_id'), table_name='life_theme_cache')
    op.drop_table('life_theme_cache')

    op.drop_constraint('life_event_timing_cache_user_id_event_type_direction_language_birth_profile_version_key', 'life_event_timing_cache', type_='unique')
    op.create_unique_constraint(
        'life_event_timing_cache_user_id_event_type_language_birth_profile_version_key',
        'life_event_timing_cache', ['user_id', 'event_type', 'language', 'birth_profile_version'],
    )
    op.drop_column('life_event_timing_cache', 'direction')

    op.drop_constraint('marriage_timing_cache_user_id_direction_language_birth_profile_version_key', 'marriage_timing_cache', type_='unique')
    op.create_unique_constraint(
        'marriage_timing_cache_user_id_language_birth_profile_version_key',
        'marriage_timing_cache', ['user_id', 'language', 'birth_profile_version'],
    )
    op.drop_column('marriage_timing_cache', 'direction')

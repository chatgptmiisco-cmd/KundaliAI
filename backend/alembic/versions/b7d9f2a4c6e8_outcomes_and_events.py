"""decision outcomes, life events, and chat personalization flag

Revision ID: b7d9f2a4c6e8
Revises: a4c6e8f1b3d5
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d9f2a4c6e8'
down_revision: Union[str, Sequence[str], None] = 'a4c6e8f1b3d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('life_decisions', sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('life_decisions', sa.Column('outcome', sa.Text(), nullable=True))
    op.add_column('life_decisions', sa.Column('outcome_captured_at', sa.DateTime(timezone=True), nullable=True))

    op.add_column(
        'chat_messages',
        sa.Column('used_personalization', sa.Boolean(), nullable=False, server_default='0'),
    )

    op.create_table('life_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('event_type', sa.String(length=32), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('month', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_life_events_user_id'), 'life_events', ['user_id'], unique=False)
    op.create_index('ix_life_events_user_year', 'life_events', ['user_id', 'year'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_life_events_user_year', table_name='life_events')
    op.drop_index(op.f('ix_life_events_user_id'), table_name='life_events')
    op.drop_table('life_events')

    op.drop_column('chat_messages', 'used_personalization')

    op.drop_column('life_decisions', 'outcome_captured_at')
    op.drop_column('life_decisions', 'outcome')
    op.drop_column('life_decisions', 'decided_at')

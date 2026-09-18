"""structured life context items + decisions (replaces free-text user_memory_notes)

Revision ID: a4c6e8f1b3d5
Revises: f1a2b3c4d5e6
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c6e8f1b3d5'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('life_context_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('domain', sa.String(length=32), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('confidence', sa.String(length=16), nullable=False),
    sa.Column('source', sa.String(length=24), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False, server_default='active'),
    sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('last_confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_life_context_items_user_id'), 'life_context_items', ['user_id'], unique=False)
    op.create_index('ix_life_context_user_domain_key', 'life_context_items', ['user_id', 'domain', 'key'], unique=False)

    op.create_table('life_decisions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('decision_type', sa.String(length=32), nullable=False),
    sa.Column('context', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False, server_default='exploring'),
    sa.Column('final_choice', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_life_decisions_user_id'), 'life_decisions', ['user_id'], unique=False)
    op.create_index('ix_life_decisions_user_type', 'life_decisions', ['user_id', 'decision_type'], unique=False)

    # Superseded by life_context_items — a real Postgres/SQLite dev
    # database only, no production users, so dropping (not just leaving
    # unused) avoids maintaining two overlapping "user memory" tables.
    op.drop_index(op.f('ix_user_memory_notes_user_id'), table_name='user_memory_notes')
    op.drop_table('user_memory_notes')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('user_memory_notes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_memory_notes_user_id'), 'user_memory_notes', ['user_id'], unique=False)

    op.drop_index('ix_life_decisions_user_type', table_name='life_decisions')
    op.drop_index(op.f('ix_life_decisions_user_id'), table_name='life_decisions')
    op.drop_table('life_decisions')

    op.drop_index('ix_life_context_user_domain_key', table_name='life_context_items')
    op.drop_index(op.f('ix_life_context_items_user_id'), table_name='life_context_items')
    op.drop_table('life_context_items')

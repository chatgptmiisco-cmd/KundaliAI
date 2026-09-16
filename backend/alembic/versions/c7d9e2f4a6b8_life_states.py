"""life states

Revision ID: c7d9e2f4a6b8
Revises: a1c4e7f0d3b6
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d9e2f4a6b8'
down_revision: Union[str, Sequence[str], None] = 'a1c4e7f0d3b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('life_states',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('marital_status', sa.String(length=16), nullable=True),
    sa.Column('marriage_date_encrypted', sa.String(length=512), nullable=True),
    sa.Column('children_count', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('pregnancy_status', sa.String(length=16), nullable=False, server_default='none'),
    sa.Column('expected_delivery_encrypted', sa.String(length=512), nullable=True),
    sa.Column('career_state', sa.String(length=16), nullable=True),
    sa.Column('business_state', sa.String(length=16), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_life_states_user_id'), 'life_states', ['user_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_life_states_user_id'), table_name='life_states')
    op.drop_table('life_states')

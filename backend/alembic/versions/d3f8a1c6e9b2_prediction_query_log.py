"""prediction query log

Revision ID: d3f8a1c6e9b2
Revises: c7d9e2f4a6b8
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3f8a1c6e9b2'
down_revision: Union[str, Sequence[str], None] = 'c7d9e2f4a6b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('prediction_query_logs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('intent', sa.String(length=32), nullable=False),
    sa.Column('direction', sa.String(length=8), nullable=True),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('result_summary', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prediction_query_logs_user_id'), 'prediction_query_logs', ['user_id'], unique=False)
    op.create_index(op.f('ix_prediction_query_logs_intent'), 'prediction_query_logs', ['intent'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_prediction_query_logs_intent'), table_name='prediction_query_logs')
    op.drop_index(op.f('ix_prediction_query_logs_user_id'), table_name='prediction_query_logs')
    op.drop_table('prediction_query_logs')

"""chat_message_embedding

Revision ID: 3f9c1a7d2b64
Revises: cf01ea8ff52b
Create Date: 2026-09-22 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f9c1a7d2b64'
down_revision: Union[str, Sequence[str], None] = 'cf01ea8ff52b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('chat_messages', sa.Column('embedding', sa.Text(), nullable=True))
    op.add_column('chat_messages', sa.Column('embedding_source_text', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chat_messages', 'embedding_source_text')
    op.drop_column('chat_messages', 'embedding')

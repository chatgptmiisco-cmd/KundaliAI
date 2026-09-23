"""Persist native conversation intent and pending questions.

Revision ID: 72ac19de8401
Revises: 3f9c1a7d2b64
"""
from alembic import op
import sqlalchemy as sa

revision = "72ac19de8401"
down_revision = "3f9c1a7d2b64"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversation_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rishi_id", sa.String(32), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("user_id", "rishi_id", name="uq_conversation_state_user_rishi"),
    )
    op.create_index("ix_conversation_states_user_id", "conversation_states", ["user_id"])


def downgrade():
    op.drop_index("ix_conversation_states_user_id", table_name="conversation_states")
    op.drop_table("conversation_states")

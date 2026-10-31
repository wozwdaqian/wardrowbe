"""Add the chat assistant's conversations, messages and undoable actions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d7f1b3c5a9e2"
down_revision: str | None = "c4e2a9d1b7f3"
branch_labels = None
depends_on = None


def _created_at():
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade():
    op.add_column(
        "body_style_recommendations",
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("body_style_recommendations.id", ondelete="SET NULL"),
        ),
    )
    op.create_table(
        "assistant_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(120)),
        *_created_at(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_assistant_conversation_user", "assistant_conversations", ["user_id", "updated_at"]
    )
    op.create_table(
        "assistant_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text()),
        sa.Column("tool_calls", postgresql.JSONB()),
        sa.Column("tool_call_id", sa.String(100)),
        sa.Column("tool_result", postgresql.JSONB()),
        *_created_at(),
    )
    op.create_index(
        "ix_assistant_message_conversation",
        "assistant_messages",
        ["conversation_id", "seq"],
    )
    op.create_table(
        "assistant_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assistant_messages.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool", sa.String(64), nullable=False),
        sa.Column("args", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("undo_data", postgresql.JSONB()),
        *_created_at(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_assistant_action_conversation",
        "assistant_actions",
        ["conversation_id", "created_at"],
    )


def downgrade():
    op.drop_table("assistant_actions")
    op.drop_table("assistant_messages")
    op.drop_table("assistant_conversations")
    op.drop_column("body_style_recommendations", "parent_id")

"""Let users attach photos to assistant messages."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5b9d2f4a8c1"
down_revision: str | None = "d7f1b3c5a9e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assistant_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assistant_messages.id", ondelete="CASCADE"),
        ),
        sa.Column("image_path", sa.String(500), nullable=False),
        sa.Column("medium_path", sa.String(500), nullable=False),
        sa.Column("thumbnail_path", sa.String(500), nullable=False),
        sa.Column("image_hash", sa.String(64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_assistant_image_message", "assistant_images", ["message_id"])


def downgrade():
    op.drop_index("ix_assistant_image_message", table_name="assistant_images")
    op.drop_table("assistant_images")

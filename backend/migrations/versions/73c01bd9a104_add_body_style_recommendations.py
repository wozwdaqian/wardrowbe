"""Add wardrobe-independent body styling history.

Revision ID: 73c01bd9a104
Revises: a7d3c9e1f5b2
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "73c01bd9a104"
down_revision: str | None = "a7d3c9e1f5b2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "body_style_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("facts", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_body_style_user_created", "body_style_recommendations", ["user_id", "created_at"]
    )


def downgrade():
    op.drop_index("ix_body_style_user_created", table_name="body_style_recommendations")
    op.drop_table("body_style_recommendations")

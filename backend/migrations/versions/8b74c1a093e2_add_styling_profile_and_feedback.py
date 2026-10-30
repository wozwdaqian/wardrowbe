"""Add personal styling preferences and feedback without rewriting reports."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8b74c1a093e2"
down_revision: str | None = "73c01bd9a104"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("styling_profile", postgresql.JSONB(), nullable=True))
    op.add_column(
        "body_style_recommendations", sa.Column("feedback", postgresql.JSONB(), nullable=True)
    )


def downgrade():
    op.drop_column("body_style_recommendations", "feedback")
    op.drop_column("users", "styling_profile")

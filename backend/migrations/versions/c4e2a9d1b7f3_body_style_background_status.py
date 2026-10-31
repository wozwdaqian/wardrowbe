"""Let body styling reports be generated in the background and marked as seen."""

import sqlalchemy as sa
from alembic import op

revision: str = "c4e2a9d1b7f3"
down_revision: str | None = "8b74c1a093e2"
branch_labels = None
depends_on = None


def upgrade():
    # Existing reports were generated synchronously, so they are complete and already seen.
    op.add_column(
        "body_style_recommendations",
        sa.Column("status", sa.String(16), nullable=False, server_default="done"),
    )
    op.add_column("body_style_recommendations", sa.Column("job_id", sa.String(64)))
    op.add_column("body_style_recommendations", sa.Column("error_code", sa.String(32)))
    op.add_column(
        "body_style_recommendations",
        sa.Column("seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.alter_column("body_style_recommendations", "seen_at", server_default=None)
    for column in ("facts", "result"):
        op.alter_column("body_style_recommendations", column, nullable=True)
    op.alter_column("body_style_recommendations", "model", nullable=True)
    op.create_index(
        "ix_body_style_user_unseen",
        "body_style_recommendations",
        ["user_id"],
        postgresql_where=sa.text("seen_at IS NULL"),
    )


def downgrade():
    op.execute("DELETE FROM body_style_recommendations WHERE status <> 'done'")
    op.drop_index("ix_body_style_user_unseen", table_name="body_style_recommendations")
    op.alter_column("body_style_recommendations", "model", nullable=False)
    for column in ("facts", "result"):
        op.alter_column("body_style_recommendations", column, nullable=False)
    for column in ("seen_at", "error_code", "job_id", "status"):
        op.drop_column("body_style_recommendations", column)

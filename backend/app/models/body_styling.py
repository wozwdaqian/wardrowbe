import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BodyStyleRecommendation(Base):
    __tablename__ = "body_style_recommendations"
    __table_args__ = (
        Index("ix_body_style_user_created", "user_id", "created_at"),
        Index(
            "ix_body_style_user_unseen",
            "user_id",
            postgresql_where=text("seen_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # AI reports are created as `pending` and completed by the worker; rule reports are `done`.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="done")
    job_id: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(32))
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    facts: Mapped[list | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    model: Mapped[str | None] = mapped_column(String(255))
    feedback: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    # Set when the report was derived from another one (e.g. one outfit regenerated).
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("body_style_recommendations.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

"""Background AI generation for body styling reports."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from arq.jobs import Job, JobStatus
from sqlalchemy import select, update

from app.models.body_styling import BodyStyleRecommendation
from app.models.user import User
from app.services.body_styling_service import complete_pending_style, style_ready_message
from app.services.notification_service import NotificationDispatcher
from app.workers.db import get_db_session
from app.workers.queues import TAGGING_QUEUE

logger = logging.getLogger(__name__)
# Generation itself is bounded at 180 s; leave room for a queue that is briefly busy.
STALE_PENDING_SECONDS = 15 * 60


async def generate_body_style_job(ctx: dict, record_id: str) -> None:
    db = get_db_session(ctx)
    try:
        record = await complete_pending_style(db, UUID(record_id))
        if record is None:
            return
        user = await db.get(User, record.user_id)
        try:
            await NotificationDispatcher(db).deliver(
                record.user_id, style_ready_message(record, user.locale)
            )
            await db.commit()
        except Exception:
            # The report is already stored; a failed notification must not fail the job.
            logger.warning("Could not notify user about a finished body styling report")
            await db.rollback()
    finally:
        await db.close()


async def recover_stale_body_styles(ctx: dict) -> None:
    """Fail pending reports whose job Redis no longer knows about, so the page stops polling."""
    redis = ctx.get("redis")
    if redis is None:
        return
    cutoff = datetime.now(UTC) - timedelta(seconds=STALE_PENDING_SECONDS)
    db = get_db_session(ctx)
    try:
        candidates = await db.execute(
            select(BodyStyleRecommendation.id, BodyStyleRecommendation.job_id).where(
                BodyStyleRecommendation.status == "pending",
                BodyStyleRecommendation.created_at < cutoff,
            )
        )
        failed = 0
        for record_id, job_id in candidates.all():
            lost = job_id is None
            if not lost:
                status = await Job(job_id, redis, _queue_name=TAGGING_QUEUE).status()
                lost = status in (JobStatus.not_found, JobStatus.complete)
            if lost:
                result = await db.execute(
                    update(BodyStyleRecommendation)
                    .where(
                        BodyStyleRecommendation.id == record_id,
                        BodyStyleRecommendation.status == "pending",
                    )
                    .values(status="failed", error_code="job_lost")
                )
                failed += result.rowcount
        await db.commit()
        if failed:
            logger.warning("Marked %d stale body styling reports as failed", failed)
    finally:
        await db.close()

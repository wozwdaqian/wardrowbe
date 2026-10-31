import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from arq.jobs import JobStatus

from app.config import get_settings
from app.models.body_styling import BodyStyleRecommendation
from app.schemas.body_styling import BodyMeasurements, BodyStyleRequest
from app.services import body_styling_service as service
from app.services.ai_service import TextGenerationResult
from app.workers import body_styling as worker
from tests.body_style_samples import sample_result

MEASUREMENTS = BodyMeasurements(height=175, chest=100, waist=90, hips=102)


@pytest.fixture
def ai(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_base_url", "http://styling-test.invalid/v1")
    monkeypatch.setattr(settings, "ai_text_model", "fixture-text")
    mocked = Mock()
    mocked.generate_text = AsyncMock(
        return_value=TextGenerationResult(
            content=json.dumps(sample_result()), model="fixture-text", endpoint="fixture"
        )
    )
    monkeypatch.setattr(service, "AIService", Mock(return_value=mocked))
    return mocked


async def pending(db_session, user, **values) -> BodyStyleRecommendation:
    record = await service.create_pending_style(db_session, user, MEASUREMENTS, BodyStyleRequest())
    for key, value in values.items():
        setattr(record, key, value)
    await db_session.commit()
    return record


@pytest.mark.asyncio
async def test_job_completes_report_and_notifies(db_session, test_user, ai):
    record = await pending(db_session, test_user)
    deliver = AsyncMock(return_value=[])
    with (
        patch.object(worker, "get_db_session", return_value=db_session),
        patch.object(db_session, "close", new_callable=AsyncMock),
        patch.object(worker.NotificationDispatcher, "deliver", deliver),
    ):
        await worker.generate_body_style_job({}, str(record.id))
    await db_session.refresh(record)
    assert record.status == "done" and record.model == "fixture-text"
    assert record.result["outfits"] and record.seen_at is None
    message = deliver.call_args.args[1]
    assert deliver.call_args.args[0] == test_user.id
    assert f"report={record.id}" in message.url
    assert message.body == record.result["summary"][:300]


@pytest.mark.asyncio
async def test_notification_failure_keeps_the_report(db_session, test_user, ai):
    record = await pending(db_session, test_user)
    with (
        patch.object(worker, "get_db_session", return_value=db_session),
        patch.object(db_session, "close", new_callable=AsyncMock),
        patch.object(
            worker.NotificationDispatcher, "deliver", AsyncMock(side_effect=RuntimeError("smtp"))
        ),
    ):
        await worker.generate_body_style_job({}, str(record.id))
    await db_session.refresh(record)
    assert record.status == "done"


class _Job:
    statuses: dict[str, JobStatus] = {}

    def __init__(self, job_id, redis, _queue_name=None):
        self.job_id = job_id

    async def status(self):
        return self.statuses.get(self.job_id, JobStatus.not_found)


@pytest.mark.asyncio
async def test_stale_pending_reports_fail_only_when_their_job_is_gone(
    db_session, test_user, monkeypatch
):
    old = datetime.now(UTC) - timedelta(hours=1)
    lost = await pending(db_session, test_user, job_id="lost", created_at=old)
    running = await pending(db_session, test_user, job_id="running", created_at=old)
    fresh = await pending(db_session, test_user, job_id="fresh")
    monkeypatch.setattr(worker, "Job", _Job)
    _Job.statuses = {"running": JobStatus.in_progress}
    with (
        patch.object(worker, "get_db_session", return_value=db_session),
        patch.object(db_session, "close", new_callable=AsyncMock),
    ):
        await worker.recover_stale_body_styles({"redis": object()})
        # Without Redis the job state cannot be verified, so nothing is condemned.
        await worker.recover_stale_body_styles({})
    for record in (lost, running, fresh):
        await db_session.refresh(record)
    assert lost.status == "failed" and lost.error_code == "job_lost"
    assert running.status == "pending"
    assert fresh.status == "pending"

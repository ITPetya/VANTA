"""Tests for self monitoring and the status endpoint.

Pure tests always run. Database tests need ``VANTA_TEST_DATABASE_URL`` (see test_queue.py).
All test data is artificial.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.api.main import app
from server.api.status import get_status_report
from server.monitoring import kuma, reporting, status
from server.monitoring.status import SourceStatus, StatusReport, evaluate_source
from server.processing import queue
from server.tests.test_queue import _ingest, db, migrated, run  # noqa: F401

NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


def _eval(last_success: datetime | None) -> SourceStatus:
    return evaluate_source(
        source_key="test_source",
        expected_interval_seconds=3600,
        last_success_at=last_success,
        last_error=None,
        now=NOW,
    )


def test_source_with_recent_success_is_online() -> None:
    assert _eval(NOW - timedelta(minutes=30)).online


def test_source_within_tolerance_is_online() -> None:
    assert _eval(NOW - timedelta(seconds=3600 * 1.5)).online


def test_silent_source_is_offline() -> None:
    assert not _eval(NOW - timedelta(seconds=3600 * 1.5 + 1)).online


def test_never_reported_source_is_offline() -> None:
    result = _eval(None)
    assert not result.online
    assert result.last_sync is None


def test_backup_marker(tmp_path: Path) -> None:
    assert status.read_last_backup(None) is None
    assert status.read_last_backup(tmp_path / "missing") is None
    marker = tmp_path / "backup.done"
    marker.touch()
    last = status.read_last_backup(marker)
    assert last is not None
    assert abs((datetime.now(UTC) - last).total_seconds()) < 60


def _report() -> StatusReport:
    return StatusReport(
        generated_at=NOW,
        sources=[_eval(NOW - timedelta(minutes=1)), _eval(None)],
        queue_length=3,
        error_queue_length=1,
        last_backup=None,
    )


def test_status_endpoint_returns_report() -> None:
    app.dependency_overrides[get_status_report] = _report
    try:
        response = TestClient(app).get("/internal/status")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["queue_length"] == 3
    assert body["error_queue_length"] == 1
    assert body["last_backup"] is None
    assert [s["online"] for s in body["sources"]] == [True, False]
    assert set(body) == {
        "generated_at",
        "sources",
        "queue_length",
        "error_queue_length",
        "last_backup",
    }


def test_status_endpoint_rejects_post() -> None:
    assert TestClient(app).post("/internal/status").status_code == 405


def test_kuma_push_states_and_skips_unconfigured() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    async def work() -> dict[str, bool]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            sources = [_eval(NOW - timedelta(minutes=1)), _eval(None)]
            sources[1] = SourceStatus("other", False, None, 60, None)
            return await kuma.push_all(
                client, {"test_source": "https://kuma.invalid/api/push/TESTTOKEN"}, sources
            )

    assert asyncio.run(work()) == {"test_source": True}
    assert len(seen) == 1
    assert seen[0].url.params["status"] == "up"


def test_kuma_push_failure_is_reported_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async def work() -> bool:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await kuma.push_source(client, "https://kuma.invalid/x", _eval(None))

    assert asyncio.run(work()) is False


def test_settings_kuma_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    from server.config import Settings

    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    monkeypatch.setenv("KUMA_PUSH_INGEST_MAIL", "https://kuma.invalid/mail")
    monkeypatch.setenv("KUMA_PUSH_INGEST_NEWS", "")
    settings = Settings(_env_file=None)
    assert settings.kuma_push_urls == {"mail": "https://kuma.invalid/mail"}


@db
def test_report_and_collect_status(migrated: str) -> None:  # noqa: F811
    async def work(sm: async_sessionmaker[AsyncSession]) -> None:
        now = datetime.now(UTC)
        async with sm() as s:
            assert await reporting.report_success(
                s, user_id=1, source_key="test_source", at=now - timedelta(minutes=5)
            )
            # An older report must not move the last success backwards.
            await reporting.report_success(
                s, user_id=1, source_key="test_source", at=now - timedelta(hours=9)
            )
            assert not await reporting.report_success(s, user_id=1, source_key="unknown")
            await s.commit()
        await _ingest(sm, b"TEST-1")
        await _ingest(sm, b"TEST-2", max_attempts=1)
        async with sm() as s:
            await queue.claim_next(s, user_id=1)  # becomes running
            await s.commit()
        async with sm() as s:
            report = await status.collect_status(s, user_id=1, now=now)
            assert report.queue_length == 2
            assert report.error_queue_length == 0
            assert [x.online for x in report.sources] == [True]
            # Second user sees nothing of the first one.
            other = await status.collect_status(s, user_id=2, now=now)
            assert other.queue_length == 0
            assert [x.online for x in other.sources] == [False]

        # Failure keeps the last success, but records the error; later silence turns it offline.
        async with sm() as s:
            await reporting.report_failure(
                s, user_id=1, source_key="test_source", error="TEST-FEHLER"
            )
            await s.commit()
        async with sm() as s:
            report = await status.collect_status(s, user_id=1, now=now + timedelta(hours=3))
            assert report.sources[0].last_error == "TEST-FEHLER"
            assert not report.sources[0].online
            assert report.sources[0].last_sync is not None
            await s.execute(text("SELECT 1"))

    run(migrated, work)

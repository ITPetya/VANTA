"""Tests for queue and error queue.

Pure tests always run. Database tests need ``VANTA_TEST_DATABASE_URL`` (see test_data_model.py)
and DROP the public schema: use an empty throwaway database only. All test data is artificial.
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.db.models import JobFailure, QueueJob, RawItem
from server.processing import queue
from server.tests.db_reset import reset_public_schema

TEST_URL = os.environ.get("VANTA_TEST_DATABASE_URL") or None


def test_backoff_grows_and_is_capped() -> None:
    assert queue.backoff_seconds(1) == 30
    assert queue.backoff_seconds(2) == 60
    assert queue.backoff_seconds(3) == 120
    assert queue.backoff_seconds(50) == queue.BACKOFF_MAX_SECONDS


db = pytest.mark.skipif(TEST_URL is None, reason="VANTA_TEST_DATABASE_URL not set")


@pytest.fixture
def migrated() -> Iterator[str]:
    """Empty database migrated to head with two users, each with one source."""
    assert TEST_URL is not None
    url = make_url(TEST_URL)
    sync_url = TEST_URL.replace("+asyncpg", "+psycopg")
    engine = create_engine(sync_url)
    reset_public_schema(engine)
    env = {
        **os.environ,
        "POSTGRES_HOST": url.host or "localhost",
        "POSTGRES_PORT": str(url.port or 5432),
        "POSTGRES_DB": url.database or "postgres",
        "POSTGRES_USER": url.username or "postgres",
        "POSTGRES_PASSWORD": url.password or "x",
    }
    subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "-c", "server/db/alembic.ini", "upgrade", "head"],
        check=True,
        env=env,
    )
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO users (display_name) VALUES ('Testnutzer A'), ('Testnutzer B')")
        )
        c.execute(
            text(
                "INSERT INTO data_sources"
                " (user_id, source_key, expected_interval_seconds, sensitivity)"
                " VALUES (1, 'test_source', 3600, 1), (2, 'test_source', 3600, 1)"
            )
        )
    engine.dispose()
    assert TEST_URL is not None
    yield TEST_URL.replace("+psycopg", "+asyncpg")


def run[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    async def main() -> T:
        engine = create_async_engine(url)
        try:
            return await work(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()

    return asyncio.run(main())


async def _ingest(
    sm: async_sessionmaker[AsyncSession], payload: bytes, user: int = 1, max_attempts: int = 5
) -> queue.IngestResult:
    async with sm() as s:
        result = await queue.ingest_raw_item(
            s,
            user_id=user,
            source_id=user,  # source ids 1 and 2 belong to user 1 and 2
            content_type="text/plain",
            payload=payload,
            sensitivity=1,
            job_type="test_job",
            max_attempts=max_attempts,
        )
        await s.commit()
        return result


@db
def test_duplicate_is_stored_once_and_creates_no_second_job(migrated: str) -> None:
    async def work(sm: async_sessionmaker[AsyncSession]) -> None:
        first = await _ingest(sm, b"TEST-PAYLOAD")
        second = await _ingest(sm, b"TEST-PAYLOAD")
        other = await _ingest(sm, b"TEST-PAYLOAD-2")
        assert not first.duplicate
        assert second.duplicate
        assert second.raw_item_id == first.raw_item_id
        assert other.raw_item_id != first.raw_item_id
        async with sm() as s:
            assert await s.scalar(select(func.count()).select_from(RawItem)) == 2
            assert await s.scalar(select(func.count()).select_from(QueueJob)) == 2
            # Raw data is stored unchanged.
            payload = await s.scalar(select(RawItem.payload).where(RawItem.id == first.raw_item_id))
            assert payload == b"TEST-PAYLOAD"

    run(migrated, work)


@db
def test_duplicate_after_processing_stays_without_consequence(migrated: str) -> None:
    async def work(sm: async_sessionmaker[AsyncSession]) -> None:
        await _ingest(sm, b"TEST-PAYLOAD")
        async with sm() as s:
            job = await queue.claim_next(s, user_id=1)
            assert job is not None
            await queue.complete(s, user_id=1, job_id=job.id)
            await s.commit()
        again = await _ingest(sm, b"TEST-PAYLOAD")
        assert again.duplicate
        async with sm() as s:
            assert await queue.claim_next(s, user_id=1) is None
            assert (await queue.count_by_status(s, user_id=1))["done"] == 1

    run(migrated, work)


@db
def test_same_content_of_two_users_is_separate(migrated: str) -> None:
    async def work(sm: async_sessionmaker[AsyncSession]) -> None:
        a = await _ingest(sm, b"TEST-PAYLOAD", user=1)
        b = await _ingest(sm, b"TEST-PAYLOAD", user=2)
        assert not a.duplicate and not b.duplicate
        async with sm() as s:
            job = await queue.claim_next(s, user_id=1)
            assert job is not None and job.raw_item_id == a.raw_item_id
            assert await queue.claim_next(s, user_id=1) is None
            assert (await queue.count_by_status(s, user_id=2))["pending"] == 1

    run(migrated, work)


@db
def test_failure_is_retried_with_backoff_then_goes_to_error_queue(migrated: str) -> None:
    async def work(sm: async_sessionmaker[AsyncSession]) -> None:
        await _ingest(sm, b"TEST-PAYLOAD", max_attempts=2)
        t0 = datetime(2030, 1, 1, tzinfo=UTC)
        async with sm() as s:
            job = await queue.claim_next(s, user_id=1, now=t0)
            assert job is not None
            assert (
                await queue.fail(s, user_id=1, job_id=job.id, error="TEST-FEHLER 1", now=t0)
                == "pending"
            )
            await s.commit()
        async with sm() as s:
            # Not due before the backoff has passed.
            assert await queue.claim_next(s, user_id=1, now=t0 + timedelta(seconds=29)) is None
            retry = await queue.claim_next(s, user_id=1, now=t0 + timedelta(seconds=30))
            assert retry is not None and retry.id == job.id and retry.attempts == 1
            assert (
                await queue.fail(s, user_id=1, job_id=job.id, error="TEST-FEHLER 2", now=t0)
                == "dead"
            )
            await s.commit()
        async with sm() as s:
            assert await queue.claim_next(s, user_id=1, now=t0 + timedelta(days=1)) is None
            row = await s.scalar(select(QueueJob))
            assert row is not None
            assert (row.status, row.attempts, row.last_error) == ("dead", 2, "TEST-FEHLER 2")
            errors = (await s.scalars(select(JobFailure.error).order_by(JobFailure.attempt))).all()
            assert list(errors) == ["TEST-FEHLER 1", "TEST-FEHLER 2"]
            assert (await queue.count_by_status(s, user_id=1))["dead"] == 1
            # Raw data survives the failure.
            assert await s.scalar(select(func.count()).select_from(RawItem)) == 1

    run(migrated, work)


@db
def test_requeue_dead_job_and_process_successfully(migrated: str) -> None:
    async def work(sm: async_sessionmaker[AsyncSession]) -> None:
        await _ingest(sm, b"TEST-PAYLOAD", max_attempts=1)
        async with sm() as s:
            job = await queue.claim_next(s, user_id=1)
            assert job is not None
            await queue.fail(s, user_id=1, job_id=job.id, error="TEST-FEHLER")
            assert await queue.requeue_dead(s, user_id=1, job_id=job.id)
            # Only dead jobs can be requeued, and only by their owner.
            assert not await queue.requeue_dead(s, user_id=1, job_id=job.id)
            await s.commit()
        async with sm() as s:
            again = await queue.claim_next(s, user_id=1)
            assert again is not None and again.attempts == 0
            await queue.complete(s, user_id=1, job_id=again.id)
            await s.commit()
            assert (await queue.count_by_status(s, user_id=1))["done"] == 1

    run(migrated, work)


@db
def test_stale_running_job_is_recovered(migrated: str) -> None:
    async def work(sm: async_sessionmaker[AsyncSession]) -> None:
        await _ingest(sm, b"TEST-PAYLOAD")
        t0 = datetime(2030, 1, 1, tzinfo=UTC)
        async with sm() as s:
            assert await queue.claim_next(s, user_id=1, now=t0) is not None
            await s.commit()
        async with sm() as s:
            assert await queue.recover_stale(s, user_id=1, now=t0 + timedelta(minutes=5)) == 0
            assert await queue.recover_stale(s, user_id=1, now=t0 + timedelta(hours=1)) == 1
            await s.commit()
        async with sm() as s:
            counts = await queue.count_by_status(s, user_id=1)
            assert counts["pending"] == 1 and counts["running"] == 0

    run(migrated, work)


@db
def test_parallel_workers_never_take_the_same_job(migrated: str) -> None:
    async def work(sm: async_sessionmaker[AsyncSession]) -> None:
        for i in range(10):
            await _ingest(sm, f"TEST-PAYLOAD-{i}".encode())

        async def worker() -> list[int]:
            taken: list[int] = []
            async with sm() as s:
                while (job := await queue.claim_next(s, user_id=1)) is not None:
                    taken.append(job.id)
                    await s.commit()  # keeps the claim, releases the row lock
            return taken

        results = await asyncio.gather(*(worker() for _ in range(4)))
        all_ids = [i for r in results for i in r]
        assert len(all_ids) == 10
        assert len(set(all_ids)) == 10

    run(migrated, work)


@db
def test_job_cannot_point_at_raw_item_of_another_user(migrated: str) -> None:
    async def work(sm: async_sessionmaker[AsyncSession]) -> None:
        from sqlalchemy.exc import IntegrityError

        item = await _ingest(sm, b"TEST-PAYLOAD", user=1)
        async with sm() as s:
            s.add(QueueJob(user_id=2, raw_item_id=item.raw_item_id, job_type="test_job"))
            with pytest.raises(IntegrityError):
                await s.commit()

    run(migrated, work)

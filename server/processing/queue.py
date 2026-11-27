"""PostgreSQL based queue with error queue.

Flow: store the raw item unchanged, enqueue a job for it in the same transaction, process
the job later. The caller owns the transaction (``commit`` after each call), so storing the
raw item and creating its job succeed or fail together.

Idempotence: a raw item is unique per ``(user_id, source_id, content_hash)`` and a job is
unique per ``(user_id, raw_item_id, job_type)``. Delivering the same data twice therefore
neither stores it twice nor creates a second job.

Jobs are claimed with ``FOR UPDATE SKIP LOCKED``, so several workers never take the same job.
Failed runs are retried with exponential backoff; after ``max_attempts`` failures a job is
``dead`` (the error queue). Dead jobs stay in the database until requeued explicitly.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.models import JobFailure, QueueJob, RawItem

DEFAULT_MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 6 * 3600
MAX_ERROR_LENGTH = 2000


@dataclass(frozen=True)
class IngestResult:
    raw_item_id: int
    # True if identical data from this source had already been stored.
    duplicate: bool


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    user_id: int
    raw_item_id: int
    job_type: str
    # Number of earlier failed runs.
    attempts: int


def backoff_seconds(failures: int) -> int:
    """Wait time before the next run after ``failures`` failed runs (30 s, 60 s, 120 s, ...)."""
    return int(min(BACKOFF_BASE_SECONDS * 2 ** max(failures - 1, 0), BACKOFF_MAX_SECONDS))


async def ingest_raw_item(
    session: AsyncSession,
    *,
    user_id: int,
    source_id: int,
    content_type: str,
    payload: bytes,
    sensitivity: int,
    job_type: str,
    occurred_at: datetime | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> IngestResult:
    """Store the raw item unchanged, then enqueue its job. Safe to call repeatedly."""
    digest = hashlib.sha256(payload).digest()
    inserted = await session.scalar(
        insert(RawItem)
        .values(
            user_id=user_id,
            source_id=source_id,
            sensitivity=sensitivity,
            content_hash=digest,
            content_type=content_type,
            payload=payload,
            occurred_at=occurred_at,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "source_id", "content_hash"])
        .returning(RawItem.id)
    )
    duplicate = inserted is None
    if inserted is None:
        raw_item_id = await session.scalar(
            select(RawItem.id).where(
                RawItem.user_id == user_id,
                RawItem.source_id == source_id,
                RawItem.content_hash == digest,
            )
        )
        assert raw_item_id is not None  # noqa: S101 - the conflict proves the row exists
    else:
        raw_item_id = inserted
    # Also for duplicates: heals a raw item whose job is missing. A no-op otherwise.
    await session.execute(
        insert(QueueJob)
        .values(
            user_id=user_id,
            raw_item_id=raw_item_id,
            job_type=job_type,
            max_attempts=max_attempts,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "raw_item_id", "job_type"])
    )
    return IngestResult(raw_item_id=raw_item_id, duplicate=duplicate)


async def claim_next(
    session: AsyncSession,
    *,
    user_id: int,
    job_type: str | None = None,
    now: datetime | None = None,
) -> ClaimedJob | None:
    """Take the oldest due job and mark it running. Returns None if nothing is due."""
    now = now or datetime.now(UTC)
    stmt = (
        select(QueueJob)
        .where(
            QueueJob.user_id == user_id,
            QueueJob.status == "pending",
            QueueJob.run_after <= now,
        )
        .order_by(QueueJob.run_after, QueueJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job_type is not None:
        stmt = stmt.where(QueueJob.job_type == job_type)
    job = await session.scalar(stmt)
    if job is None:
        return None
    job.status = "running"
    job.locked_at = now
    await session.flush()
    return ClaimedJob(
        id=job.id,
        user_id=job.user_id,
        raw_item_id=job.raw_item_id,
        job_type=job.job_type,
        attempts=job.attempts,
    )


async def complete(session: AsyncSession, *, user_id: int, job_id: int) -> None:
    """Mark a running job as done."""
    await session.execute(
        update(QueueJob)
        .where(QueueJob.user_id == user_id, QueueJob.id == job_id, QueueJob.status == "running")
        .values(status="done", locked_at=None, last_error=None, finished_at=func.now())
    )


async def fail(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int,
    error: str,
    now: datetime | None = None,
) -> str:
    """Record a failed run. Returns the new status: ``pending`` (retry) or ``dead``."""
    now = now or datetime.now(UTC)
    job = await session.scalar(
        select(QueueJob)
        .where(QueueJob.user_id == user_id, QueueJob.id == job_id, QueueJob.status == "running")
        .with_for_update()
    )
    if job is None:
        raise LookupError(f"no running job {job_id} for user {user_id}")
    message = error[:MAX_ERROR_LENGTH]
    job.attempts += 1
    job.last_error = message
    job.locked_at = None
    session.add(JobFailure(user_id=user_id, job_id=job_id, attempt=job.attempts, error=message))
    if job.attempts >= job.max_attempts:
        job.status = "dead"
        job.finished_at = now
    else:
        job.status = "pending"
        job.run_after = now + timedelta(seconds=backoff_seconds(job.attempts))
    await session.flush()
    return job.status


async def recover_stale(
    session: AsyncSession,
    *,
    user_id: int,
    timeout: timedelta = timedelta(minutes=15),
    now: datetime | None = None,
) -> int:
    """Return jobs of crashed workers to ``pending``. A lost run counts as a failure."""
    now = now or datetime.now(UTC)
    stale = (
        await session.scalars(
            select(QueueJob.id).where(
                QueueJob.user_id == user_id,
                QueueJob.status == "running",
                QueueJob.locked_at < now - timeout,
            )
        )
    ).all()
    recovered = 0
    for job_id in stale:
        try:
            await fail(
                session,
                user_id=user_id,
                job_id=job_id,
                error="worker did not finish in time",
                now=now,
            )
            recovered += 1
        except LookupError:
            continue  # finished in the meantime
    return recovered


async def requeue_dead(session: AsyncSession, *, user_id: int, job_id: int) -> bool:
    """Give a dead job a fresh start (manual action by the operator)."""
    result = await session.execute(
        update(QueueJob)
        .where(QueueJob.user_id == user_id, QueueJob.id == job_id, QueueJob.status == "dead")
        .values(status="pending", attempts=0, run_after=func.now(), finished_at=None)
    )
    return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]


async def count_by_status(session: AsyncSession, *, user_id: int) -> dict[str, int]:
    """Number of jobs per status, for the status endpoint."""
    rows = await session.execute(
        select(QueueJob.status, func.count())
        .where(QueueJob.user_id == user_id)
        .group_by(QueueJob.status)
    )
    counts = {"pending": 0, "running": 0, "done": 0, "dead": 0}
    counts.update({status: n for status, n in rows.all()})
    return counts

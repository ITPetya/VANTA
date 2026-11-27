"""Self monitoring: is every source alive, how full are the queues, when was the last backup.

``evaluate_source`` is pure (easy to test). ``collect_status`` reads the database.
A source that never reported a success counts as offline: silence is an error.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.models import DataSource, QueueJob

# A source may be this much later than its expected interval before it counts as silent.
TOLERANCE_FACTOR = 1.5


@dataclass(frozen=True)
class SourceStatus:
    source_key: str
    online: bool
    last_sync: datetime | None
    expected_interval_seconds: int
    last_error: str | None


@dataclass(frozen=True)
class StatusReport:
    generated_at: datetime
    sources: list[SourceStatus]
    queue_length: int
    error_queue_length: int
    last_backup: datetime | None


def evaluate_source(
    *,
    source_key: str,
    expected_interval_seconds: int,
    last_success_at: datetime | None,
    last_error: str | None,
    now: datetime,
) -> SourceStatus:
    """Online only if the last success is within interval times tolerance."""
    online = False
    if last_success_at is not None:
        age = (now - last_success_at).total_seconds()
        online = age <= expected_interval_seconds * TOLERANCE_FACTOR
    return SourceStatus(
        source_key=source_key,
        online=online,
        last_sync=last_success_at,
        expected_interval_seconds=expected_interval_seconds,
        last_error=last_error,
    )


def read_last_backup(marker_path: Path | None) -> datetime | None:
    """Time of the last backup: modification time of a marker file the backup job touches."""
    if marker_path is None:
        return None
    try:
        return datetime.fromtimestamp(marker_path.stat().st_mtime, tz=UTC)
    except OSError:
        return None


async def collect_status(
    session: AsyncSession,
    *,
    user_id: int,
    backup_marker_path: Path | None = None,
    now: datetime | None = None,
) -> StatusReport:
    now = now or datetime.now(UTC)
    rows = await session.execute(
        select(DataSource).where(DataSource.user_id == user_id).order_by(DataSource.source_key)
    )
    sources = [
        evaluate_source(
            source_key=s.source_key,
            expected_interval_seconds=s.expected_interval_seconds,
            last_success_at=s.last_success_at,
            last_error=s.last_error,
            now=now,
        )
        for s in rows.scalars()
    ]
    counts = dict(
        (
            await session.execute(
                select(QueueJob.status, func.count())
                .where(QueueJob.user_id == user_id)
                .group_by(QueueJob.status)
            )
        )
        .tuples()
        .all()
    )
    return StatusReport(
        generated_at=now,
        sources=sources,
        # Open work: waiting or currently running.
        queue_length=counts.get("pending", 0) + counts.get("running", 0),
        error_queue_length=counts.get("dead", 0),
        last_backup=read_last_backup(backup_marker_path),
    )

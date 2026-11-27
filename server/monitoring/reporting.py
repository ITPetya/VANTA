"""Sources report their runs here. Silence is an error, so every run is recorded.

The caller owns the transaction (``commit`` after each call), like in the queue module.
All statements filter by ``user_id``.
"""

from datetime import UTC, datetime

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.models import DataSource

MAX_ERROR_LENGTH = 500


async def report_success(
    session: AsyncSession, *, user_id: int, source_key: str, at: datetime | None = None
) -> bool:
    """Record a successful run. Returns False if the source is unknown.

    ``last_success_at`` never moves backwards, so a late or repeated report is harmless.
    """
    now = at or datetime.now(UTC)
    result = await session.execute(
        update(DataSource)
        .where(DataSource.user_id == user_id, DataSource.source_key == source_key)
        .values(
            last_success_at=func.greatest(func.coalesce(DataSource.last_success_at, now), now),
            last_attempt_at=now,
            last_error=None,
        )
    )
    return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]


async def report_failure(
    session: AsyncSession,
    *,
    user_id: int,
    source_key: str,
    error: str,
    at: datetime | None = None,
) -> bool:
    """Record a failed run (the last success stays untouched). Returns False if unknown."""
    now = at or datetime.now(UTC)
    result = await session.execute(
        update(DataSource)
        .where(DataSource.user_id == user_id, DataSource.source_key == source_key)
        .values(last_attempt_at=now, last_error=error[:MAX_ERROR_LENGTH])
    )
    return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]

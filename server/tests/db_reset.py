"""Shared helper to reset the throwaway test database.

Only used by tests that run with ``VANTA_TEST_DATABASE_URL``. Never point that
variable at a real VANTA database.
"""

import time

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

_RESET_SQL = "DROP SCHEMA public CASCADE; CREATE SCHEMA public"

# Other sessions (left over from previous tests or TimescaleDB background
# workers) can hold locks on tables in "public". Terminating them first and
# retrying on deadlocks makes the reset deterministic.
_TERMINATE_SQL = (
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
    " WHERE datname = current_database() AND pid <> pg_backend_pid()"
    " AND backend_type = 'client backend'"
)


def reset_public_schema(engine: Engine, attempts: int = 5) -> None:
    """Drop and recreate the public schema, retrying on lock conflicts."""
    for attempt in range(1, attempts + 1):
        try:
            with engine.begin() as c:
                c.execute(text(_TERMINATE_SQL))
            with engine.begin() as c:
                c.execute(text("SET lock_timeout = '10s'"))
                c.execute(text(_RESET_SQL))
            return
        except OperationalError:
            if attempt == attempts:
                raise
            time.sleep(0.5 * attempt)

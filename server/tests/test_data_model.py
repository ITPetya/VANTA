"""Tests for data model version 1.

Pure metadata tests always run. Database tests need a PostgreSQL with TimescaleDB and only
run when ``VANTA_TEST_DATABASE_URL`` is set. They DROP the public schema: use an empty
throwaway database only.
All test data is clearly artificial.
"""

import hashlib
import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from server.db.models import Base
from server.tests.db_reset import reset_public_schema

TEST_URL = os.environ.get("VANTA_TEST_DATABASE_URL") or None


def test_every_table_has_user_id() -> None:
    for name, table in Base.metadata.tables.items():
        if name == "users":
            assert "id" in table.c
        else:
            assert "user_id" in table.c, name
            assert not table.c.user_id.nullable, name


def test_user_id_is_part_of_time_series_key() -> None:
    pk = {c.name for c in Base.metadata.tables["measurements"].primary_key.columns}
    assert {"user_id", "time"} <= pk


def test_expected_tables_exist() -> None:
    assert set(Base.metadata.tables) == {
        "users",
        "data_sources",
        "raw_items",
        "measurements",
        "feedback",
        "action_log",
        "queue_jobs",
        "job_failures",
    }


pytestmark_db = pytest.mark.skipif(TEST_URL is None, reason="VANTA_TEST_DATABASE_URL not set")


@pytest.fixture
def conn() -> Iterator[Connection]:
    assert TEST_URL is not None
    engine = create_engine(TEST_URL.replace("+asyncpg", "+psycopg"))
    reset_public_schema(engine)
    yield engine.connect()
    engine.dispose()


def _digest(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _seed(c: Connection) -> None:
    c.execute(text("INSERT INTO users (display_name) VALUES ('Testnutzer A'), ('Testnutzer B')"))
    c.execute(
        text(
            "INSERT INTO data_sources (user_id, source_key, expected_interval_seconds, sensitivity)"
            " VALUES (1, 'test_source', 3600, 1), (2, 'test_source', 3600, 1)"
        )
    )


@pytestmark_db
def test_migration_roundtrip_and_constraints(conn: Connection) -> None:
    assert TEST_URL is not None
    # Run Alembic as a subprocess with the test database settings.
    from sqlalchemy.engine import make_url

    url = make_url(TEST_URL)
    env = {
        **os.environ,
        "POSTGRES_HOST": url.host or "localhost",
        "POSTGRES_PORT": str(url.port or 5432),
        "POSTGRES_DB": url.database or "postgres",
        "POSTGRES_USER": url.username or "postgres",
        "POSTGRES_PASSWORD": url.password or "x",
    }

    def alembic(*args: str) -> None:
        subprocess.run(  # noqa: S603
            [sys.executable, "-m", "alembic", "-c", "server/db/alembic.ini", *args],
            check=True,
            env=env,
        )

    alembic("upgrade", "head")
    hyper = conn.execute(
        text(
            "SELECT count(*) FROM timescaledb_information.hypertables"
            " WHERE hypertable_name = 'measurements'"
        )
    ).scalar()
    assert hyper == 1

    _seed(conn)
    now = datetime(2000, 1, 1, tzinfo=UTC)
    payload = b"TEST-PAYLOAD"
    raw = (
        "INSERT INTO raw_items"
        " (user_id, source_id, sensitivity, content_hash, content_type, payload)"
        " VALUES (:u, :s, :lvl, :h, 'text/plain', :p)"
    )
    conn.execute(text(raw), {"u": 1, "s": 1, "lvl": 1, "h": _digest(payload), "p": payload})
    conn.commit()

    # Duplicate by checksum is rejected; the same content for another user is fine.
    with pytest.raises(IntegrityError):
        conn.execute(text(raw), {"u": 1, "s": 1, "lvl": 1, "h": _digest(payload), "p": payload})
    conn.rollback()
    conn.execute(text(raw), {"u": 2, "s": 2, "lvl": 1, "h": _digest(payload), "p": payload})
    conn.commit()

    # Sensitivity outside 1 to 3 and wrong hash length are rejected.
    for lvl, h in [(4, _digest(b"a")), (0, _digest(b"b")), (1, b"short")]:
        with pytest.raises(IntegrityError):
            conn.execute(text(raw), {"u": 1, "s": 1, "lvl": lvl, "h": h, "p": b"x"})
        conn.rollback()

    # A user cannot reference the source of another user.
    with pytest.raises(IntegrityError):
        conn.execute(text(raw), {"u": 1, "s": 2, "lvl": 1, "h": _digest(b"c"), "p": b"x"})
    conn.rollback()

    # Time series: insert works, duplicate point is rejected.
    meas = (
        "INSERT INTO measurements (user_id, source_id, metric_type, time, value, unit, sensitivity)"
        " VALUES (1, 1, 'test_metric', :t, 42.5, 'testunit', 1)"
    )
    conn.execute(text(meas), {"t": now})
    conn.commit()
    with pytest.raises(IntegrityError):
        conn.execute(text(meas), {"t": now})
    conn.rollback()

    # Feedback: unknown reaction is rejected, repeated reaction is rejected.
    fb = "INSERT INTO feedback (user_id, message_id, reaction) VALUES (1, 'test-msg-1', :r)"
    conn.execute(text(fb), {"r": "useful"})
    conn.commit()
    for reaction in ("useful", "unknown"):
        with pytest.raises(IntegrityError):
            conn.execute(text(fb), {"r": reaction})
        conn.rollback()

    conn.execute(
        text("INSERT INTO action_log (user_id, actor, action) VALUES (1, 'test', 'test_action')")
    )
    conn.commit()

    alembic("downgrade", "0001")
    left = conn.execute(
        text("SELECT count(*) FROM pg_tables WHERE tablename = 'raw_items'")
    ).scalar()
    assert left == 0

"""Data model version 1.

Rules that apply to every table:
- ``user_id`` is part of every table and every key, even with a single user.
- References between tables are composite ``(user_id, id)`` keys, so a row can never
  point at data of another user.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Stable constraint names keep migrations predictable.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SENSITIVITY_CHECK = "sensitivity BETWEEN 1 AND 3"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _now() -> Any:
    return func.now()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())


class DataSource(Base):
    """A data source (connector) with its expected frequency and last successful run."""

    __tablename__ = "data_sources"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),  # target of composite foreign keys
        UniqueConstraint("user_id", "source_key"),
        CheckConstraint("expected_interval_seconds > 0", name="interval_positive"),
        CheckConstraint(SENSITIVITY_CHECK, name="sensitivity_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Stable technical name, e.g. "mail" or "healthkit".
    source_key: Mapped[str] = mapped_column(String(100))
    # Silence beyond this interval (plus tolerance, applied by monitoring) is an error.
    expected_interval_seconds: Mapped[int] = mapped_column(Integer)
    # Default sensitivity of the data this source delivers (1 to 3).
    sensitivity: Mapped[int] = mapped_column(SmallInteger)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())


class RawItem(Base):
    """Every incoming piece of information, stored unchanged before any processing."""

    __tablename__ = "raw_items"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "source_id"], ["data_sources.user_id", "data_sources.id"]),
        # The checksum makes re-delivery harmless (idempotent ingest).
        UniqueConstraint("user_id", "source_id", "content_hash"),
        UniqueConstraint("user_id", "id"),  # target of composite foreign keys
        CheckConstraint(SENSITIVITY_CHECK, name="sensitivity_range"),
        CheckConstraint("octet_length(content_hash) = 32", name="hash_is_sha256"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source_id: Mapped[int] = mapped_column(BigInteger)
    # When VANTA received the item, and when it happened according to the source.
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sensitivity: Mapped[int] = mapped_column(SmallInteger)
    # SHA-256 of the unchanged payload.
    content_hash: Mapped[bytes] = mapped_column(LargeBinary)
    content_type: Mapped[str] = mapped_column(String(100))
    # Unchanged payload. Levels 2 and 3 are encrypted via server/crypto.py
    # (wiring follows with the connectors).
    payload: Mapped[bytes] = mapped_column(LargeBinary)


class Measurement(Base):
    """Time series of measured values (TimescaleDB hypertable on ``time``)."""

    __tablename__ = "measurements"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "source_id"], ["data_sources.user_id", "data_sources.id"]),
        CheckConstraint(SENSITIVITY_CHECK, name="sensitivity_range"),
    )

    # The primary key doubles as duplicate protection and must contain the partition column.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    source_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    metric_type: Mapped[str] = mapped_column(String(100), primary_key=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    sensitivity: Mapped[int] = mapped_column(SmallInteger)
    # Origin of the value; no foreign key because raw items may be archived independently.
    raw_item_id: Mapped[int | None] = mapped_column(BigInteger)


class Feedback(Base):
    """Reaction of the user to a delivered message."""

    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "reaction IN ('opened', 'useful', 'not_useful', 'dismissed', 'ignored')",
            name="reaction_known",
        ),
        CheckConstraint("read_seconds >= 0", name="read_seconds_nonnegative"),
        UniqueConstraint("user_id", "message_id", "reaction"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Identifier of the delivered message (messages table follows with the delivery milestone).
    message_id: Mapped[str] = mapped_column(String(100))
    reaction: Mapped[str] = mapped_column(String(32))
    read_seconds: Mapped[int | None] = mapped_column(Integer)
    given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())


class ActionLog(Base):
    """Log of every action the system takes (append only)."""

    __tablename__ = "action_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
    # Component that acted, e.g. "ingest.mail" or "delivery".
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100))
    # Why the action happened (traceability).
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


JOB_STATUSES = ("pending", "running", "done", "dead")


class QueueJob(Base):
    """Work item on the PostgreSQL based queue.

    Lifecycle: ``pending`` -> ``running`` -> ``done``. A failed run goes back to ``pending``
    with a later ``run_after`` (backoff). After ``max_attempts`` failures the job becomes
    ``dead``: that is the error queue. Dead jobs are never deleted, only requeued by hand.
    """

    __tablename__ = "queue_jobs"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "raw_item_id"], ["raw_items.user_id", "raw_items.id"]),
        # One job per raw item and job type: re-delivery cannot create duplicate work.
        UniqueConstraint("user_id", "raw_item_id", "job_type"),
        UniqueConstraint("user_id", "id"),  # target of composite foreign keys
        CheckConstraint("status IN ('pending', 'running', 'done', 'dead')", name="status_known"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        # Claiming looks for due pending jobs.
        Index("ix_queue_jobs_pending", "run_after", postgresql_where=text("status = 'pending'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    raw_item_id: Mapped[int] = mapped_column(BigInteger)
    job_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    # Number of runs that ended in failure so far (the failure count).
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="5")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobFailure(Base):
    """History of every failed run of a job (append only)."""

    __tablename__ = "job_failures"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "job_id"], ["queue_jobs.user_id", "queue_jobs.id"]),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    job_id: Mapped[int] = mapped_column(BigInteger)
    attempt: Mapped[int] = mapped_column(Integer)
    error: Mapped[str] = mapped_column(Text)
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())

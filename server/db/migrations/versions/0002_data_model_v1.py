"""Data model version 1: users, sources, raw items, measurements, feedback, action log

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_table(
        "action_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_action_log_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_log")),
    )
    op.create_table(
        "data_sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column("expected_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("sensitivity", sa.SmallInteger(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "expected_interval_seconds > 0", name=op.f("ck_data_sources_interval_positive")
        ),
        sa.CheckConstraint(
            "sensitivity BETWEEN 1 AND 3", name=op.f("ck_data_sources_sensitivity_range")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_data_sources_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_sources")),
        sa.UniqueConstraint("user_id", "id", name=op.f("uq_data_sources_user_id_id")),
        sa.UniqueConstraint(
            "user_id", "source_key", name=op.f("uq_data_sources_user_id_source_key")
        ),
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.String(length=100), nullable=False),
        sa.Column("reaction", sa.String(length=32), nullable=False),
        sa.Column("read_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "given_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reaction IN ('opened', 'useful', 'not_useful', 'dismissed', 'ignored')",
            name=op.f("ck_feedback_reaction_known"),
        ),
        sa.CheckConstraint("read_seconds >= 0", name=op.f("ck_feedback_read_seconds_nonnegative")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_feedback_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback")),
        sa.UniqueConstraint(
            "user_id",
            "message_id",
            "reaction",
            name=op.f("uq_feedback_user_id_message_id_reaction"),
        ),
    )
    op.create_table(
        "measurements",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("metric_type", sa.String(length=100), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("sensitivity", sa.SmallInteger(), nullable=False),
        sa.Column("raw_item_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "sensitivity BETWEEN 1 AND 3", name=op.f("ck_measurements_sensitivity_range")
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "source_id"],
            ["data_sources.user_id", "data_sources.id"],
            name=op.f("fk_measurements_user_id_source_id_data_sources"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_measurements_user_id_users")
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "source_id", "metric_type", "time", name=op.f("pk_measurements")
        ),
    )
    op.create_table(
        "raw_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sensitivity", sa.SmallInteger(), nullable=False),
        sa.Column("content_hash", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint(
            "octet_length(content_hash) = 32", name=op.f("ck_raw_items_hash_is_sha256")
        ),
        sa.CheckConstraint(
            "sensitivity BETWEEN 1 AND 3", name=op.f("ck_raw_items_sensitivity_range")
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "source_id"],
            ["data_sources.user_id", "data_sources.id"],
            name=op.f("fk_raw_items_user_id_source_id_data_sources"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_raw_items_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_items")),
        sa.UniqueConstraint(
            "user_id",
            "source_id",
            "content_hash",
            name=op.f("uq_raw_items_user_id_source_id_content_hash"),
        ),
    )
    # Time series: partitioned by time. The primary key contains the partition column.
    op.execute(
        "SELECT create_hypertable('measurements', 'time', chunk_time_interval => INTERVAL '7 days')"
    )


def downgrade() -> None:
    op.drop_table("raw_items")
    op.drop_table("measurements")
    op.drop_table("feedback")
    op.drop_table("data_sources")
    op.drop_table("action_log")
    op.drop_table("users")

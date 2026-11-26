"""Queue and error queue: queue_jobs, job_failures

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(op.f("uq_raw_items_user_id_id"), "raw_items", ["user_id", "id"])
    op.create_table(
        "queue_jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("raw_item_id", sa.BigInteger(), nullable=False),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column(
            "run_after", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'done', 'dead')",
            name=op.f("ck_queue_jobs_status_known"),
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_queue_jobs_attempts_nonnegative")),
        sa.CheckConstraint("max_attempts >= 1", name=op.f("ck_queue_jobs_max_attempts_positive")),
        sa.ForeignKeyConstraint(
            ["user_id", "raw_item_id"],
            ["raw_items.user_id", "raw_items.id"],
            name=op.f("fk_queue_jobs_user_id_raw_item_id_raw_items"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_queue_jobs_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_queue_jobs")),
        sa.UniqueConstraint(
            "user_id",
            "raw_item_id",
            "job_type",
            name=op.f("uq_queue_jobs_user_id_raw_item_id_job_type"),
        ),
        sa.UniqueConstraint("user_id", "id", name=op.f("uq_queue_jobs_user_id_id")),
    )
    op.create_index(
        "ix_queue_jobs_pending",
        "queue_jobs",
        ["run_after"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "job_failures",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "job_id"],
            ["queue_jobs.user_id", "queue_jobs.id"],
            name=op.f("fk_job_failures_user_id_job_id_queue_jobs"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_job_failures_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_failures")),
    )


def downgrade() -> None:
    op.drop_table("job_failures")
    op.drop_index("ix_queue_jobs_pending", table_name="queue_jobs")
    op.drop_table("queue_jobs")
    op.drop_constraint(op.f("uq_raw_items_user_id_id"), "raw_items", type_="unique")

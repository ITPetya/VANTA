"""Device authentication: devices, registration_codes, request_nonces, rejected_requests

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "octet_length(public_key) = 65", name=op.f("ck_devices_public_key_length")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_devices_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_devices")),
        sa.UniqueConstraint("user_id", "id", name=op.f("uq_devices_user_id_id")),
        sa.UniqueConstraint("user_id", "public_key", name=op.f("uq_devices_user_id_public_key")),
    )
    op.create_table(
        "registration_codes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_registration_codes_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registration_codes")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_registration_codes_code_hash")),
    )
    op.create_table(
        "request_nonces",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("nonce", sa.String(length=32), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "device_id"],
            ["devices.user_id", "devices.id"],
            name=op.f("fk_request_nonces_user_id_device_id_devices"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_request_nonces_user_id_users")
        ),
        sa.PrimaryKeyConstraint("user_id", "device_id", "nonce", name=op.f("pk_request_nonces")),
    )
    op.create_index("ix_request_nonces_seen_at", "request_nonces", ["seen_at"])
    op.create_table(
        "rejected_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=200), nullable=False),
        sa.Column("rejected_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_rejected_requests_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rejected_requests")),
    )
    op.create_index("ix_rejected_requests_rejected_at", "rejected_requests", ["rejected_at"])


def downgrade() -> None:
    op.drop_index("ix_rejected_requests_rejected_at", table_name="rejected_requests")
    op.drop_table("rejected_requests")
    op.drop_index("ix_request_nonces_seen_at", table_name="request_nonces")
    op.drop_table("request_nonces")
    op.drop_table("registration_codes")
    op.drop_table("devices")

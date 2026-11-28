"""Device authentication: signed requests and registration (see docs/SIGNATUR.md).

``require_device`` is the dependency for every public endpoint. A rejected request is
logged in ``rejected_requests`` and answered with a generic 401, so the response does not
reveal why it failed.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from server.api import signing
from server.config import get_settings
from server.db.models import Device, RegistrationCode, RejectedRequest, RequestNonce
from server.db.session import get_session

logger = logging.getLogger("vanta.auth")

MAX_BODY_BYTES = 1_048_576
MAX_LOGGED_PATH = 200


@dataclass(frozen=True)
class AuthenticatedDevice:
    device_id: int
    user_id: int


def hash_code(code: str) -> str:
    """Registration codes are compared by hash; dashes and case are ignored."""
    normalized = code.replace("-", "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def create_registration_code(
    session: AsyncSession, *, user_id: int, ttl_seconds: int, now: datetime | None = None
) -> str:
    """Create a one-time code. The plain code is returned once and never stored."""
    current = now or datetime.now(UTC)
    raw = secrets.token_hex(10)  # 80 bits
    session.add(
        RegistrationCode(
            user_id=user_id,
            code_hash=hash_code(raw),
            expires_at=current + timedelta(seconds=ttl_seconds),
        )
    )
    await session.flush()
    return "-".join(raw[i : i + 5] for i in range(0, 20, 5))


async def register_device(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    public_key: bytes,
    now: datetime | None = None,
) -> int | None:
    """Consume a code and register the device. Returns the device id, or None if the code is
    unknown, used or expired. The code is consumed by one atomic UPDATE, so it works once."""
    current = now or datetime.now(UTC)
    user_id = await session.scalar(
        update(RegistrationCode)
        .where(
            RegistrationCode.code_hash == hash_code(code),
            RegistrationCode.used_at.is_(None),
            RegistrationCode.expires_at > current,
        )
        .values(used_at=current)
        .returning(RegistrationCode.user_id)
    )
    if user_id is None:
        return None
    device = Device(user_id=user_id, name=name, public_key=public_key)
    session.add(device)
    await session.flush()
    return device.id


async def revoke_device(session: AsyncSession, *, user_id: int, device_id: int) -> bool:
    result = await session.execute(
        update(Device).where(Device.user_id == user_id, Device.id == device_id).values(revoked=True)
    )
    return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]


async def _log_rejection(
    session: AsyncSession, request: Request, reason: str, device_id: int | None
) -> None:
    """Record the rejection. Only method, path and reason are stored, never the content."""
    await session.rollback()
    session.add(
        RejectedRequest(
            user_id=get_settings().vanta_user_id,
            device_id=device_id,
            reason=reason,
            method=request.method[:16],
            path=request.url.path[:MAX_LOGGED_PATH],
        )
    )
    await session.commit()
    logger.warning("rejected request: %s %s (%s)", request.method, request.url.path, reason)


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="unauthorized")


async def require_device(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> AuthenticatedDevice:
    """Verify the signature, timestamp and nonce of a request."""
    settings = get_settings()
    headers = request.headers
    device_header = headers.get("x-vanta-device", "")
    timestamp = headers.get("x-vanta-timestamp", "")
    nonce = headers.get("x-vanta-nonce", "")
    signature = headers.get("x-vanta-signature", "")

    async def reject(reason: str, device_id: int | None = None) -> HTTPException:
        await _log_rejection(session, request, reason, device_id)
        return _unauthorized()

    if not (device_header.isascii() and device_header.isdigit() and len(device_header) <= 18):
        raise await reject("bad_device_header")
    device_id = int(device_header)
    if not signing.TIMESTAMP_RE.match(timestamp):
        raise await reject("bad_timestamp_header", device_id)
    if not signing.NONCE_RE.match(nonce):
        raise await reject("bad_nonce_header", device_id)
    if not signature:
        raise await reject("missing_signature", device_id)

    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise await reject("body_too_large", device_id)
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise await reject("body_too_large", device_id)

    device = await session.scalar(select(Device).where(Device.id == device_id))
    if device is None:
        raise await reject("unknown_device", device_id)
    if device.revoked:
        raise await reject("device_revoked", device_id)

    path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    message = signing.signing_message(
        method=request.method, path=path, timestamp=timestamp, nonce=nonce, body=body
    )
    # Signature first: only authentic requests may touch the nonce table.
    if not signing.verify_signature(device.public_key, signature, message):
        raise await reject("bad_signature", device_id)

    now = datetime.now(UTC)
    if abs(now.timestamp() - int(timestamp)) > settings.vanta_auth_tolerance_seconds:
        raise await reject("timestamp_out_of_range", device_id)

    inserted = await session.execute(
        insert(RequestNonce)
        .values(user_id=device.user_id, device_id=device.id, nonce=nonce, seen_at=now)
        .on_conflict_do_nothing()
    )
    if inserted.rowcount == 0:  # type: ignore[attr-defined]
        raise await reject("replayed_nonce", device_id)

    # Nonces older than twice the tolerance can no longer pass the timestamp check.
    cutoff = now - timedelta(seconds=2 * settings.vanta_auth_tolerance_seconds)
    await session.execute(
        delete(RequestNonce).where(
            RequestNonce.user_id == device.user_id, RequestNonce.seen_at < cutoff
        )
    )
    await session.execute(
        update(Device)
        .where(Device.user_id == device.user_id, Device.id == device.id)
        .values(last_seen_at=now)
    )
    await session.commit()
    return AuthenticatedDevice(device_id=device.id, user_id=device.user_id)

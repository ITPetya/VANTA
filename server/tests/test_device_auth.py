"""Tests for device registration and signed requests.

Database tests need ``VANTA_TEST_DATABASE_URL`` (see test_data_model.py) and DROP the public
schema: use an empty throwaway database only. All keys and names are artificial.
"""

import base64
import os
import secrets
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Iterator

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from server.api import signing
from server.api.main import create_app
from server.config import get_settings
from server.db.session import get_session
from server.tests.db_reset import reset_public_schema

TEST_URL = os.environ.get("VANTA_TEST_DATABASE_URL") or None
pytestmark = pytest.mark.skipif(TEST_URL is None, reason="VANTA_TEST_DATABASE_URL not set")


class Env:
    def __init__(self, client: TestClient, sync_url: str) -> None:
        self.client = client
        self.sync_url = sync_url
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.public_b64 = base64.b64encode(
            self.private.public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
            )
        ).decode()

    def sql(self, statement: str) -> list[tuple[object, ...]]:
        engine = create_engine(self.sync_url)
        try:
            with engine.begin() as c:
                result = c.execute(text(statement))
                return [tuple(r) for r in result.fetchall()] if result.returns_rows else []
        finally:
            engine.dispose()

    def new_code(self, ttl: int = 600) -> str:
        import asyncio

        from server.api.auth import create_registration_code

        async def go() -> str:
            engine = create_async_engine(self.sync_url.replace("+psycopg", "+asyncpg"))
            try:
                async with AsyncSession(engine) as s:
                    code = await create_registration_code(s, user_id=1, ttl_seconds=ttl)
                    await s.commit()
                    return code
            finally:
                await engine.dispose()

        return asyncio.run(go())

    def register(self, code: str | None = None, name: str = "Testgerät") -> int:
        response = self.client.post(
            "/internal/devices/register",
            json={"code": code or self.new_code(), "name": name, "public_key": self.public_b64},
        )
        assert response.status_code == 200, response.text
        return int(response.json()["device_id"])

    def signed(
        self,
        device_id: int,
        method: str = "GET",
        path: str = "/v1/ping",
        body: bytes = b"",
        timestamp: int | None = None,
        nonce: str | None = None,
        key: ec.EllipticCurvePrivateKey | None = None,
    ) -> dict[str, str]:
        ts = str(int(time.time()) if timestamp is None else timestamp)
        n = nonce or secrets.token_hex(16)
        message = signing.signing_message(
            method=method, path=path, timestamp=ts, nonce=n, body=body
        )
        signature = (key or self.private).sign(message, ec.ECDSA(hashes.SHA256()))
        return {
            "X-Vanta-Device": str(device_id),
            "X-Vanta-Timestamp": ts,
            "X-Vanta-Nonce": n,
            "X-Vanta-Signature": base64.b64encode(signature).decode(),
        }

    def rejections(self) -> list[str]:
        return [str(r[0]) for r in self.sql("SELECT reason FROM rejected_requests ORDER BY id")]


@pytest.fixture
def env() -> Iterator[Env]:
    assert TEST_URL is not None
    url = make_url(TEST_URL)
    sync_url = TEST_URL.replace("+asyncpg", "+psycopg")
    engine = create_engine(sync_url)
    reset_public_schema(engine)
    subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "-c", "server/db/alembic.ini", "upgrade", "head"],
        check=True,
        env={
            **os.environ,
            "POSTGRES_HOST": url.host or "localhost",
            "POSTGRES_PORT": str(url.port or 5432),
            "POSTGRES_DB": url.database or "postgres",
            "POSTGRES_USER": url.username or "postgres",
            "POSTGRES_PASSWORD": url.password or "x",
        },
    )
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (display_name) VALUES ('Testnutzer A')"))
    engine.dispose()

    os.environ.setdefault("POSTGRES_PASSWORD", "unused-test-value")
    get_settings.cache_clear()
    async_engine = create_async_engine(TEST_URL.replace("+psycopg", "+asyncpg"), poolclass=NullPool)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)

    async def override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override
    yield Env(TestClient(app), sync_url)
    get_settings.cache_clear()


def test_registered_device_can_call_public_endpoint(env: Env) -> None:
    device_id = env.register()
    response = env.client.get("/v1/ping", headers=env.signed(device_id))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert env.sql("SELECT last_seen_at IS NOT NULL FROM devices") == [(True,)]
    assert env.rejections() == []


def test_unsigned_request_is_rejected_and_logged(env: Env) -> None:
    assert env.client.get("/v1/ping").status_code == 401
    assert env.rejections() == ["bad_device_header"]


def test_unknown_device_is_rejected(env: Env) -> None:
    response = env.client.get("/v1/ping", headers=env.signed(999))
    assert response.status_code == 401
    assert env.rejections() == ["unknown_device"]


def test_wrong_key_is_rejected(env: Env) -> None:
    device_id = env.register()
    other = ec.generate_private_key(ec.SECP256R1())
    response = env.client.get("/v1/ping", headers=env.signed(device_id, key=other))
    assert response.status_code == 401
    assert env.rejections() == ["bad_signature"]


def test_tampered_path_method_and_body_are_rejected(env: Env) -> None:
    device_id = env.register()
    # Signed as POST, sent as GET: method differs.
    headers = env.signed(device_id, method="POST")
    assert env.client.get("/v1/ping", headers=headers).status_code == 401
    # Signature of an empty body replayed with a body.
    headers = env.signed(device_id)
    assert env.client.request("GET", "/v1/ping", headers=headers, content=b"x").status_code == 401
    # Query string is part of the path.
    headers = env.signed(device_id, path="/v1/ping")
    assert env.client.get("/v1/ping?a=1", headers=headers).status_code == 401
    assert env.rejections() == ["bad_signature"] * 3


def test_signed_query_string_is_accepted(env: Env) -> None:
    device_id = env.register()
    headers = env.signed(device_id, path="/v1/ping?a=1")
    assert env.client.get("/v1/ping?a=1", headers=headers).status_code == 200


def test_replayed_request_is_rejected(env: Env) -> None:
    device_id = env.register()
    headers = env.signed(device_id)
    assert env.client.get("/v1/ping", headers=headers).status_code == 200
    assert env.client.get("/v1/ping", headers=headers).status_code == 401
    assert env.rejections() == ["replayed_nonce"]


def test_old_and_future_timestamps_are_rejected(env: Env) -> None:
    device_id = env.register()
    now = int(time.time())
    for ts in (now - 3600, now + 3600):
        response = env.client.get("/v1/ping", headers=env.signed(device_id, timestamp=ts))
        assert response.status_code == 401
    assert env.rejections() == ["timestamp_out_of_range"] * 2
    # Rejected requests do not burn nonces.
    assert env.sql("SELECT count(*) FROM request_nonces") == [(0,)]


def test_malformed_headers_are_rejected(env: Env) -> None:
    device_id = env.register()
    good = env.signed(device_id)
    for key, value, reason in (
        ("X-Vanta-Nonce", "short", "bad_nonce_header"),
        ("X-Vanta-Timestamp", "abc", "bad_timestamp_header"),
        ("X-Vanta-Device", "1; DROP", "bad_device_header"),
    ):
        response = env.client.get("/v1/ping", headers={**good, key: value})
        assert response.status_code == 401
        assert env.rejections()[-1] == reason


def test_revoked_device_is_rejected(env: Env) -> None:
    device_id = env.register()
    env.sql("UPDATE devices SET revoked = true")
    response = env.client.get("/v1/ping", headers=env.signed(device_id))
    assert response.status_code == 401
    assert env.rejections() == ["device_revoked"]


def test_old_nonces_are_cleaned_up(env: Env) -> None:
    device_id = env.register()
    assert env.client.get("/v1/ping", headers=env.signed(device_id)).status_code == 200
    env.sql("UPDATE request_nonces SET seen_at = now() - interval '1 hour'")
    assert env.client.get("/v1/ping", headers=env.signed(device_id)).status_code == 200
    assert env.sql("SELECT count(*) FROM request_nonces") == [(1,)]


def test_registration_code_works_once(env: Env) -> None:
    code = env.new_code()
    env.register(code)
    response = env.client.post(
        "/internal/devices/register",
        json={"code": code, "name": "Zweites Testgerät", "public_key": env.public_b64},
    )
    assert response.status_code == 403
    assert env.sql("SELECT count(*) FROM devices") == [(1,)]


def test_code_is_stored_only_as_hash(env: Env) -> None:
    code = env.new_code()
    stored = str(env.sql("SELECT code_hash FROM registration_codes")[0][0])
    assert len(stored) == 64
    assert code.replace("-", "") not in stored


def test_expired_and_unknown_codes_are_rejected(env: Env) -> None:
    expired = env.new_code()
    env.sql("UPDATE registration_codes SET expires_at = now() - interval '1 minute'")
    for code in (expired, "aaaaa-bbbbb-ccccc-ddddd"):
        response = env.client.post(
            "/internal/devices/register",
            json={"code": code, "name": "Testgerät", "public_key": env.public_b64},
        )
        assert response.status_code == 403
    assert env.sql("SELECT count(*) FROM devices") == [(0,)]


def test_registration_rejects_bad_input(env: Env) -> None:
    code = env.new_code()
    base = {"code": code, "name": "Testgerät", "public_key": env.public_b64}
    bad_payloads = [
        {**base, "extra": 1},
        {**base, "public_key": base64.b64encode(b"\x04" + b"\x01" * 64).decode()},
        {**base, "public_key": "x" * 88},
        {**base, "name": ""},
        {**base, "name": "n" * 101},
        {k: v for k, v in base.items() if k != "name"},
    ]
    for payload in bad_payloads:
        assert env.client.post("/internal/devices/register", json=payload).status_code == 422
    assert env.sql("SELECT count(*) FROM devices") == [(0,)]
    # The code is still usable after the failed attempts.
    env.register(code)

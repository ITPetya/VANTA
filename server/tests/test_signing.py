"""Tests for the signing format (pure, no database). All keys are generated per test."""

import base64

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from server.api import signing


def make_key() -> tuple[ec.EllipticCurvePrivateKey, bytes]:
    private = ec.generate_private_key(ec.SECP256R1())
    raw = private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return private, raw


def sign(private: ec.EllipticCurvePrivateKey, message: bytes) -> str:
    return base64.b64encode(private.sign(message, ec.ECDSA(hashes.SHA256()))).decode()


NONCE = "0123456789abcdef0123456789abcdef"


def test_message_format_is_fixed() -> None:
    message = signing.signing_message(
        method="post", path="/v1/x?a=1", timestamp="1700000000", nonce=NONCE, body=b""
    )
    empty_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert message == (f"VANTA-SIG-1\nPOST\n/v1/x?a=1\n1700000000\n{NONCE}\n{empty_hash}".encode())


def test_valid_signature_verifies() -> None:
    private, raw = make_key()
    message = signing.signing_message(
        method="GET", path="/v1/ping", timestamp="1", nonce=NONCE, body=b""
    )
    assert signing.verify_signature(raw, sign(private, message), message)


@pytest.mark.parametrize(
    "change",
    [
        {"method": "POST"},
        {"path": "/v1/other"},
        {"timestamp": "2"},
        {"nonce": "f" * 32},
        {"body": b"x"},
    ],
)
def test_any_changed_field_breaks_signature(change: dict[str, object]) -> None:
    private, raw = make_key()
    fields: dict[str, object] = {
        "method": "GET",
        "path": "/v1/ping",
        "timestamp": "1",
        "nonce": NONCE,
        "body": b"",
    }
    signature = sign(private, signing.signing_message(**fields))  # type: ignore[arg-type]
    changed = signing.signing_message(**{**fields, **change})  # type: ignore[arg-type]
    assert not signing.verify_signature(raw, signature, changed)


def test_other_key_and_garbage_are_rejected() -> None:
    private, _ = make_key()
    _, other_raw = make_key()
    message = b"m"
    assert not signing.verify_signature(other_raw, sign(private, message), message)
    _, raw = make_key()
    assert not signing.verify_signature(raw, "not base64!!", message)
    assert not signing.verify_signature(raw, "AAAA", message)
    assert not signing.verify_signature(raw, "A" * 300, message)
    assert not signing.verify_signature(b"\x04" + b"\x00" * 64, sign(private, message), message)


def test_public_key_validation() -> None:
    _, raw = make_key()
    assert signing.decode_public_key(base64.b64encode(raw).decode()) == raw
    with pytest.raises(ValueError):
        signing.decode_public_key("%%%")
    with pytest.raises(ValueError):
        signing.decode_public_key(base64.b64encode(raw[:-1]).decode())
    with pytest.raises(ValueError):
        # Point that is not on the curve.
        signing.decode_public_key(base64.b64encode(b"\x04" + b"\x01" * 64).decode())

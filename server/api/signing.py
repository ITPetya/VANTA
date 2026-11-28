"""Request signing format shared with the app (see docs/SIGNATUR.md).

Pure functions without database access, so the format is easy to test and to reimplement.
"""

import base64
import binascii
import hashlib
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

SIGNATURE_VERSION = "VANTA-SIG-1"
PUBLIC_KEY_LENGTH = 65  # X9.62 uncompressed point on P-256
MAX_SIGNATURE_B64_LENGTH = 200  # DER encoded P-256 signatures are at most 72 bytes

NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
TIMESTAMP_RE = re.compile(r"^[0-9]{1,12}$")


def body_hash(body: bytes) -> str:
    """Lowercase hex SHA-256 of the raw request body (empty body is hashed as well)."""
    return hashlib.sha256(body).hexdigest()


def signing_message(*, method: str, path: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    """The exact bytes that are signed. ``path`` includes the query string, if any."""
    lines = [SIGNATURE_VERSION, method.upper(), path, timestamp, nonce, body_hash(body)]
    return "\n".join(lines).encode("utf-8")


def load_public_key(raw: bytes) -> ec.EllipticCurvePublicKey:
    """Load an uncompressed P-256 point. Raises ValueError for anything else."""
    if len(raw) != PUBLIC_KEY_LENGTH or raw[0] != 0x04:
        raise ValueError("public key must be an uncompressed P-256 point (65 bytes)")
    return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)


def decode_public_key(value: str) -> bytes:
    """Decode and validate a base64 public key. Raises ValueError if invalid."""
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("public key is not valid base64") from exc
    load_public_key(raw)
    return raw


def verify_signature(public_key: bytes, signature_b64: str, message: bytes) -> bool:
    """Verify an ECDSA P-256 / SHA-256 signature (DER encoded, base64)."""
    if len(signature_b64) > MAX_SIGNATURE_B64_LENGTH:
        return False
    try:
        signature = base64.b64decode(signature_b64, validate=True)
        key = load_public_key(public_key)
        key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
    except (binascii.Error, ValueError, InvalidSignature):
        return False
    return True

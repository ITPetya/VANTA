"""Encryption by sensitivity level (see SECURITY.md).

- Level 1: stored unencrypted.
- Level 2 and 3: AES-256-GCM (authenticated), each level with its own key file.

Key files hold one or more lines ``<version>:<base64 of 32 random bytes>``. The highest
version encrypts, all listed versions decrypt, so a key can be rotated by adding a line.

The key used for the data is derived per user from the master key (HKDF with the user id),
and the user id and level are bound into the ciphertext as associated data. A blob of one
user can therefore never be decrypted as data of another user. Own key files per user
(ROADMAP section 13) only need a different ``KeyProvider``; the blob format stays the same.

Blob format: ``key version (2 bytes, big endian) | nonce (12 bytes) | ciphertext + tag``.
"""

import base64
import binascii
import os
import struct
from pathlib import Path
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from server.config import Settings, get_settings

KEY_SIZE = 32
NONCE_SIZE = 12
_VERSION_STRUCT = struct.Struct(">H")
_MAX_VERSION = 0xFFFF
_ENCRYPTED_LEVELS = (2, 3)


class CryptoError(Exception):
    """Base class for all encryption errors."""


class KeyMissingError(CryptoError):
    """A key (file) needed for the requested operation is not configured or not readable."""


class KeyFormatError(CryptoError):
    """A key file exists but its content is invalid."""


class DecryptionError(CryptoError):
    """Data is damaged, was tampered with, or belongs to another user, level or key."""


class KeyProvider(Protocol):
    """Source of keys. Replace to use separate key files per user."""

    def current_version(self, user_id: int, level: int) -> int: ...

    def get_key(self, user_id: int, level: int, version: int) -> bytes: ...


def parse_key_file(text: str, *, source: str = "key file") -> dict[int, bytes]:
    """Parse ``<version>:<base64 key>`` lines. Empty lines and ``#`` comments are ignored."""
    keys: dict[int, bytes] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        version_text, sep, key_text = line.partition(":")
        try:
            if not sep:
                raise ValueError("missing ':'")
            version = int(version_text.strip())
            key = base64.b64decode(key_text.strip(), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise KeyFormatError(
                f"{source}, line {number}: expected '<version>:<base64 key>'"
            ) from exc
        if not 1 <= version <= _MAX_VERSION:
            raise KeyFormatError(f"{source}, line {number}: version must be 1 to {_MAX_VERSION}")
        if len(key) != KEY_SIZE:
            raise KeyFormatError(f"{source}, line {number}: key must be exactly {KEY_SIZE} bytes")
        if version in keys:
            raise KeyFormatError(f"{source}, line {number}: duplicate version {version}")
        keys[version] = key
    if not keys:
        raise KeyFormatError(f"{source}: contains no key")
    return keys


class FileKeyProvider:
    """Reads one master key file per level and derives a key per user from it."""

    def __init__(self, paths: dict[int, Path | None]) -> None:
        self._paths = paths
        self._cache: dict[int, dict[int, bytes]] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> "FileKeyProvider":
        return cls({2: settings.vanta_key_level2_path, 3: settings.vanta_key_level3_path})

    def _master_keys(self, level: int) -> dict[int, bytes]:
        if level not in self._cache:
            path = self._paths.get(level)
            env_name = f"VANTA_KEY_LEVEL{level}_PATH"
            if path is None:
                raise KeyMissingError(
                    f"No key configured for level {level}: set {env_name} in .env "
                    "(see docs/VERSCHLUESSELUNG.md)"
                )
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise KeyMissingError(
                    f"Key file for level {level} not readable ({env_name}={path}): "
                    f"{exc.strerror or exc}"
                ) from exc
            self._cache[level] = parse_key_file(text, source=f"key file level {level}")
        return self._cache[level]

    def current_version(self, user_id: int, level: int) -> int:
        return max(self._master_keys(level))

    def get_key(self, user_id: int, level: int, version: int) -> bytes:
        master = self._master_keys(level).get(version)
        if master is None:
            raise KeyMissingError(f"Key version {version} for level {level} not in key file")
        return HKDF(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE,
            salt=None,
            info=f"vanta-v1|level={level}|user={user_id}".encode(),
        ).derive(master)


def _aad(user_id: int, level: int, version: int) -> bytes:
    return f"vanta-v1|user={user_id}|level={level}|key={version}".encode()


def _check_level(level: int) -> None:
    if level not in (1, *_ENCRYPTED_LEVELS):
        raise ValueError(f"Invalid sensitivity level: {level}")


class Encryptor:
    """Encrypts and decrypts payloads according to their sensitivity level."""

    def __init__(self, provider: KeyProvider) -> None:
        self._provider = provider

    def encrypt(self, user_id: int, level: int, plaintext: bytes) -> bytes:
        """Return the storable form. Level 1 is returned unchanged."""
        _check_level(level)
        if level == 1:
            return plaintext
        version = self._provider.current_version(user_id, level)
        key = self._provider.get_key(user_id, level, version)
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, _aad(user_id, level, version))
        return _VERSION_STRUCT.pack(version) + nonce + ciphertext

    def decrypt(self, user_id: int, level: int, blob: bytes) -> bytes:
        """Return the plaintext of a stored value. Level 1 is returned unchanged."""
        _check_level(level)
        if level == 1:
            return blob
        header = _VERSION_STRUCT.size + NONCE_SIZE
        if len(blob) < header + 16:
            raise DecryptionError("Encrypted value is too short")
        (version,) = _VERSION_STRUCT.unpack_from(blob)
        nonce = blob[_VERSION_STRUCT.size : header]
        key = self._provider.get_key(user_id, level, version)
        try:
            return AESGCM(key).decrypt(nonce, blob[header:], _aad(user_id, level, version))
        except InvalidTag as exc:
            raise DecryptionError(
                "Decryption failed: data damaged, or wrong user, level or key"
            ) from exc

    @staticmethod
    def key_version(blob: bytes) -> int:
        """Key version a level 2 or 3 blob was encrypted with (for rotation)."""
        if len(blob) < _VERSION_STRUCT.size:
            raise DecryptionError("Encrypted value is too short")
        return int(_VERSION_STRUCT.unpack_from(blob)[0])


def get_encryptor() -> Encryptor:
    """Encryptor with keys from the files configured in .env."""
    return Encryptor(FileKeyProvider.from_settings(get_settings()))


def generate_key_line(version: int = 1) -> str:
    """One new random key line for a key file."""
    return f"{version}:{base64.b64encode(os.urandom(KEY_SIZE)).decode()}"

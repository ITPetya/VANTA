from pathlib import Path

import pytest

from server.crypto import (
    DecryptionError,
    Encryptor,
    FileKeyProvider,
    KeyFormatError,
    KeyMissingError,
    generate_key_line,
    parse_key_file,
)


def make_encryptor(tmp_path: Path, l2: str | None = None, l3: str | None = None) -> Encryptor:
    paths: dict[int, Path | None] = {2: None, 3: None}
    for level, content in ((2, l2), (3, l3)):
        if content is not None:
            path = tmp_path / f"l{level}.key"
            path.write_text(content)
            paths[level] = path
    return Encryptor(FileKeyProvider(paths))


@pytest.fixture
def enc(tmp_path: Path) -> Encryptor:
    return make_encryptor(tmp_path, generate_key_line(), generate_key_line())


def test_level1_unencrypted_and_needs_no_key(tmp_path: Path) -> None:
    enc = make_encryptor(tmp_path)
    assert enc.encrypt(1, 1, b"news") == b"news"
    assert enc.decrypt(1, 1, b"news") == b"news"


@pytest.mark.parametrize("level", [2, 3])
def test_roundtrip_and_no_plaintext(enc: Encryptor, level: int) -> None:
    blob = enc.encrypt(1, level, b"artificial secret")
    assert b"artificial secret" not in blob
    assert enc.decrypt(1, level, blob) == b"artificial secret"


def test_nonce_random(enc: Encryptor) -> None:
    assert enc.encrypt(1, 2, b"x") != enc.encrypt(1, 2, b"x")


def test_levels_use_separate_keys(tmp_path: Path) -> None:
    line = generate_key_line()
    other = generate_key_line()
    a = make_encryptor(tmp_path, line, other)
    blob = a.encrypt(1, 2, b"x")
    # Same bytes presented as level 3 must fail (different key and bound level).
    with pytest.raises(DecryptionError):
        a.decrypt(1, 3, blob)


def test_other_user_cannot_decrypt(enc: Encryptor) -> None:
    blob = enc.encrypt(1, 2, b"x")
    with pytest.raises(DecryptionError):
        enc.decrypt(2, 2, blob)


def test_tampering_detected(enc: Encryptor) -> None:
    blob = bytearray(enc.encrypt(1, 3, b"x"))
    blob[-1] ^= 1
    with pytest.raises(DecryptionError):
        enc.decrypt(1, 3, bytes(blob))
    with pytest.raises(DecryptionError):
        enc.decrypt(1, 3, b"short")


def test_key_version_stored_and_rotation(tmp_path: Path) -> None:
    v1 = generate_key_line(1)
    old = make_encryptor(tmp_path, v1, v1)
    old_blob = old.encrypt(1, 2, b"x")
    assert Encryptor.key_version(old_blob) == 1

    rotated = make_encryptor(tmp_path, f"{v1}\n{generate_key_line(2)}\n", v1)
    assert rotated.decrypt(1, 2, old_blob) == b"x"
    new_blob = rotated.encrypt(1, 2, b"x")
    assert Encryptor.key_version(new_blob) == 2
    assert rotated.decrypt(1, 2, new_blob) == b"x"


def test_unknown_version_reported(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a = make_encryptor(tmp_path / "a", generate_key_line(2), generate_key_line())
    b = make_encryptor(tmp_path / "b", generate_key_line(1), generate_key_line())
    with pytest.raises(KeyMissingError, match="version 2"):
        b.decrypt(1, 2, a.encrypt(1, 2, b"x"))


def test_missing_key_path_has_clear_message(tmp_path: Path) -> None:
    enc = make_encryptor(tmp_path)
    with pytest.raises(KeyMissingError, match="VANTA_KEY_LEVEL2_PATH"):
        enc.encrypt(1, 2, b"x")
    with pytest.raises(KeyMissingError, match="VANTA_KEY_LEVEL3_PATH"):
        enc.encrypt(1, 3, b"x")


def test_missing_key_file_has_clear_message(tmp_path: Path) -> None:
    enc = Encryptor(FileKeyProvider({2: tmp_path / "nope.key", 3: None}))
    with pytest.raises(KeyMissingError, match="not readable"):
        enc.encrypt(1, 2, b"x")


def test_invalid_level(enc: Encryptor) -> None:
    with pytest.raises(ValueError):
        enc.encrypt(1, 4, b"x")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "# only comment",
        "garbage",
        "1:not base64!!",
        "1:AAAA",
        "0:" + "A" * 43 + "=",
        f"1:{'A' * 43}=\n1:{'A' * 43}=",
    ],
)
def test_invalid_key_files(text: str) -> None:
    with pytest.raises(KeyFormatError):
        parse_key_file(text)


def test_generated_key_parses() -> None:
    assert list(parse_key_file("# c\n" + generate_key_line(3))) == [3]

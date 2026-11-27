"""Tests for the encrypted backup. All data is artificial; the dump is a fake command."""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from server.backup import backup
from server.backup.backup import BackupError, decrypt_backup, run_backup
from server.monitoring.status import read_last_backup

NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
PAYLOAD = "artificial dump content " * 100


def _dump(text: str = PAYLOAD) -> list[str]:
    return [sys.executable, "-c", f"import sys; sys.stdout.write({text!r})"]


@pytest.fixture
def key(tmp_path: Path) -> Path:
    path = tmp_path / "keys" / "backup.key"
    path.parent.mkdir()
    path.write_text("artificial-test-passphrase\n")
    return path


def test_roundtrip_encrypts_and_restores(tmp_path: Path, key: Path) -> None:
    result = run_backup(dump_command=_dump(), key_path=key, backup_dir=tmp_path / "b", now=NOW)
    assert result.path.name == "vanta-20300101T120000Z.dump.enc"
    assert b"artificial dump content" not in result.path.read_bytes()
    assert oct(result.path.stat().st_mode & 0o777) == "0o600"
    out = tmp_path / "restored.dump"
    decrypt_backup(backup_path=result.path, key_path=key, output_path=out)
    assert out.read_text() == PAYLOAD


def test_wrong_key_cannot_decrypt(tmp_path: Path, key: Path) -> None:
    result = run_backup(dump_command=_dump(), key_path=key, backup_dir=tmp_path / "b", now=NOW)
    other = tmp_path / "other.key"
    other.write_text("another-passphrase\n")
    out = tmp_path / "restored.dump"
    with pytest.raises(BackupError):
        decrypt_backup(backup_path=result.path, key_path=other, output_path=out)
    assert not out.exists()


def test_success_touches_marker(tmp_path: Path, key: Path) -> None:
    marker = tmp_path / "state" / "last_backup"
    run_backup(
        dump_command=_dump(), key_path=key, backup_dir=tmp_path / "b", marker_path=marker, now=NOW
    )
    assert read_last_backup(marker) == NOW


def test_failed_dump_leaves_no_file_and_no_marker(tmp_path: Path, key: Path) -> None:
    marker = tmp_path / "last_backup"
    failing = [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"]
    with pytest.raises(BackupError, match="boom"):
        run_backup(
            dump_command=failing,
            key_path=key,
            backup_dir=tmp_path / "b",
            marker_path=marker,
            now=NOW,
        )
    assert list((tmp_path / "b").iterdir()) == []
    assert not marker.exists()


def test_failed_backup_keeps_old_backups(tmp_path: Path, key: Path) -> None:
    directory = tmp_path / "b"
    run_backup(dump_command=_dump(), key_path=key, backup_dir=directory, keep=1, now=NOW)
    with pytest.raises(BackupError):
        run_backup(
            dump_command=[sys.executable, "-c", "import sys; sys.exit(1)"],
            key_path=key,
            backup_dir=directory,
            keep=1,
            now=NOW + timedelta(days=1),
        )
    assert len(backup.list_backups(directory)) == 1


def test_empty_dump_is_an_error(tmp_path: Path, key: Path) -> None:
    with pytest.raises(BackupError, match="empty"):
        run_backup(dump_command=_dump(""), key_path=key, backup_dir=tmp_path / "b", now=NOW)
    assert list((tmp_path / "b").iterdir()) == []


def test_missing_or_empty_key_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(BackupError):
        run_backup(dump_command=_dump(), key_path=tmp_path / "nope", backup_dir=tmp_path / "b")
    empty = tmp_path / "empty.key"
    empty.write_text("\n")
    with pytest.raises(BackupError):
        run_backup(dump_command=_dump(), key_path=empty, backup_dir=tmp_path / "b")


def test_retention_keeps_newest(tmp_path: Path, key: Path) -> None:
    directory = tmp_path / "b"
    for day in range(5):
        run_backup(
            dump_command=_dump(),
            key_path=key,
            backup_dir=directory,
            keep=3,
            now=NOW + timedelta(days=day),
        )
    names = [p.name for p in backup.list_backups(directory)]
    assert names == [
        "vanta-20300103T120000Z.dump.enc",
        "vanta-20300104T120000Z.dump.enc",
        "vanta-20300105T120000Z.dump.enc",
    ]


def test_retention_ignores_foreign_files_and_rejects_zero(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("keep me")
    (tmp_path / "vanta-20300101T000000Z.dump.enc").write_bytes(b"x")
    assert backup.apply_retention(tmp_path, 1) == []
    assert (tmp_path / "notes.txt").exists()
    with pytest.raises(ValueError):
        backup.apply_retention(tmp_path, 0)


def test_dump_command_uses_settings_without_password() -> None:
    command = backup.default_dump_command(host="h", port=5432, user="u", database="d")
    assert command[:2] == ["pg_dump", "-Fc"]
    assert "PGPASSWORD" not in " ".join(command)


def test_cli_run_and_decrypt(tmp_path: Path, key: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from server.config import get_settings

    marker = tmp_path / "marker"
    monkeypatch.setenv("POSTGRES_PASSWORD", "artificial-test-password")
    monkeypatch.setenv("VANTA_BACKUP_DIR", str(tmp_path / "b"))
    monkeypatch.setenv("VANTA_BACKUP_KEY_PATH", str(key))
    monkeypatch.setenv("VANTA_BACKUP_MARKER_PATH", str(marker))
    monkeypatch.setenv(
        "VANTA_BACKUP_DUMP_COMMAND",
        f"{sys.executable} -c \"print('artificial dump content, long enough')\"",
    )
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    try:
        assert backup.main(["run"]) == 0
        assert marker.exists()
        (file,) = backup.list_backups(tmp_path / "b")
        out = tmp_path / "out.dump"
        assert backup.main(["decrypt", str(file), str(out)]) == 0
        assert out.read_text().strip() == "artificial dump content, long enough"
        assert backup.main(["bogus"]) == 2
    finally:
        get_settings.cache_clear()
    assert os.environ["POSTGRES_PASSWORD"]

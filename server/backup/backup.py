"""Encrypted database backup with retention and success report.

Pipeline: dump command -> ``openssl enc`` (AES-256-CBC, PBKDF2, passphrase from a key file)
-> ``<name>.part`` -> atomic rename. Only after a complete, verified file exists are the
marker touched (self monitoring reads its mtime as "last backup") and old backups removed.
A failed run leaves old backups and the marker untouched: silence stays visible.

The passphrase is passed as ``-pass file:<path>``, never on the command line.
The backup key must be stored separately from the backups (see docs/BACKUP.md).
"""

import logging
import os
import shlex
import subprocess  # noqa: S404
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("vanta.backup")

BACKUP_PREFIX = "vanta-"
BACKUP_SUFFIX = ".dump.enc"
PBKDF2_ITERATIONS = "600000"
_CIPHER = ["-aes-256-cbc", "-pbkdf2", "-iter", PBKDF2_ITERATIONS, "-salt"]
DEFAULT_KEEP = 14


class BackupError(Exception):
    """The backup or restore step failed."""


@dataclass(frozen=True)
class BackupResult:
    path: Path
    size_bytes: int
    removed: list[Path]


def default_dump_command(*, host: str, port: int, user: str, database: str) -> list[str]:
    """Custom-format dump; the password comes from PGPASSWORD in the environment."""
    return ["pg_dump", "-Fc", "-h", host, "-p", str(port), "-U", user, "-d", database]


def list_backups(directory: Path) -> list[Path]:
    """Backups in the directory, oldest first (names contain a sortable UTC timestamp)."""
    return sorted(directory.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"))


def apply_retention(directory: Path, keep: int) -> list[Path]:
    """Delete all but the newest ``keep`` backups. Returns the deleted files."""
    if keep < 1:
        raise ValueError("keep must be at least 1")
    backups = list_backups(directory)
    old = backups[:-keep] if len(backups) > keep else []
    for path in old:
        path.unlink()
    return old


def _check_key(key_path: Path) -> None:
    try:
        if not key_path.read_text().strip():
            raise BackupError(f"Backup key file is empty: {key_path}")
    except OSError as exc:
        raise BackupError(f"Backup key file not readable: {key_path}") from exc


def run_backup(
    *,
    dump_command: list[str],
    key_path: Path,
    backup_dir: Path,
    keep: int = DEFAULT_KEEP,
    marker_path: Path | None = None,
    env: dict[str, str] | None = None,
    now: datetime | None = None,
) -> BackupResult:
    """Create one encrypted backup. Raises ``BackupError``; nothing is reported on failure."""
    if keep < 1:
        raise ValueError("keep must be at least 1")
    _check_key(key_path)
    now = now or datetime.now(UTC)
    backup_dir.mkdir(parents=True, exist_ok=True)
    final = backup_dir / f"{BACKUP_PREFIX}{now.strftime('%Y%m%dT%H%M%SZ')}{BACKUP_SUFFIX}"
    part = final.with_name(final.name + ".part")
    proc_env = {**os.environ, **(env or {})}

    try:
        with part.open("wb") as out:
            os.fchmod(out.fileno(), 0o600)
            dump = subprocess.Popen(  # noqa: S603
                dump_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=proc_env
            )
            enc = subprocess.Popen(  # noqa: S603
                ["openssl", "enc", *_CIPHER, "-pass", f"file:{key_path}"],  # noqa: S607
                stdin=dump.stdout,
                stdout=out,
                stderr=subprocess.PIPE,
            )
            assert dump.stdout is not None  # noqa: S101
            dump.stdout.close()  # let the dump get SIGPIPE if openssl dies
            enc_err = enc.communicate()[1]
            dump_err = dump.stderr.read() if dump.stderr else b""
            dump.wait()
        if dump.returncode != 0:
            raise BackupError(f"Dump failed (exit {dump.returncode}): {_tail(dump_err)}")
        if enc.returncode != 0:
            raise BackupError(f"Encryption failed (exit {enc.returncode}): {_tail(enc_err)}")
        # openssl always writes a header ("Salted__" + salt = 16 bytes) plus padding.
        if part.stat().st_size <= 32:
            raise BackupError("Backup is empty, the dump produced no data")
        part.replace(final)
    except (OSError, BackupError) as exc:
        part.unlink(missing_ok=True)
        if isinstance(exc, BackupError):
            raise
        raise BackupError(f"Backup failed: {exc}") from exc

    # Success: report first, then clean up. Retention never runs after a failed backup.
    if marker_path is not None:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.touch()
        os.utime(marker_path, (now.timestamp(), now.timestamp()))
    removed = apply_retention(backup_dir, keep)
    return BackupResult(path=final, size_bytes=final.stat().st_size, removed=removed)


def decrypt_backup(*, backup_path: Path, key_path: Path, output_path: Path) -> None:
    """Decrypt a backup into a dump file that ``pg_restore`` can read."""
    _check_key(key_path)
    part = output_path.with_name(output_path.name + ".part")
    try:
        with part.open("wb") as out:
            os.fchmod(out.fileno(), 0o600)
            proc = subprocess.run(  # noqa: S603
                [  # noqa: S607
                    "openssl",
                    "enc",
                    "-d",
                    *_CIPHER[:-1],
                    "-in",
                    str(backup_path),
                    "-pass",
                    f"file:{key_path}",
                ],
                stdout=out,
                stderr=subprocess.PIPE,
                check=False,
            )
        if proc.returncode != 0:
            raise BackupError(
                f"Decryption failed (wrong key or damaged file): {_tail(proc.stderr)}"
            )
        part.replace(output_path)
    except OSError as exc:
        raise BackupError(f"Decryption failed: {exc}") from exc
    finally:
        part.unlink(missing_ok=True)


def _tail(data: bytes, limit: int = 300) -> str:
    return data.decode("utf-8", errors="replace").strip()[-limit:]


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m server.backup.backup run`` or ``decrypt <backup> <output>``."""
    from server.config import get_settings

    args = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    if settings.vanta_backup_key_path is None:
        logger.error("VANTA_BACKUP_KEY_PATH is not set")
        return 2
    try:
        if args == ["run"]:
            if settings.vanta_backup_dir is None:
                logger.error("VANTA_BACKUP_DIR is not set")
                return 2
            command = (
                shlex.split(settings.vanta_backup_dump_command)
                if settings.vanta_backup_dump_command
                else default_dump_command(
                    host=settings.postgres_host,
                    port=settings.postgres_port,
                    user=settings.postgres_user,
                    database=settings.postgres_db,
                )
            )
            result = run_backup(
                dump_command=command,
                key_path=settings.vanta_backup_key_path,
                backup_dir=settings.vanta_backup_dir,
                keep=settings.vanta_backup_keep,
                marker_path=settings.vanta_backup_marker_path,
                env={"PGPASSWORD": settings.postgres_password.get_secret_value()},
            )
            logger.info(
                "Backup ok: %s (%d bytes), removed %d old",
                result.path.name,
                result.size_bytes,
                len(result.removed),
            )
            return 0
        if len(args) == 3 and args[0] == "decrypt":
            decrypt_backup(
                backup_path=Path(args[1]),
                key_path=settings.vanta_backup_key_path,
                output_path=Path(args[2]),
            )
            logger.info("Decrypted to %s", args[2])
            return 0
    except BackupError as exc:
        logger.error("%s", exc)
        return 1
    logger.error("Usage: run | decrypt <backup-file> <output-file>")
    return 2


if __name__ == "__main__":
    sys.exit(main())

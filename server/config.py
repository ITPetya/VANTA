"""Server configuration, read from environment variables (.env)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """Settings needed by the server core. Real values only come from .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    vanta_timezone: str = "Europe/Berlin"
    vanta_user_id: int = Field(default=1, ge=1)

    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "vanta"
    postgres_user: str = "vanta"
    # No default on purpose: the server must not start with an empty password.
    postgres_password: SecretStr = Field(min_length=1)

    # Paths to key files (never the keys themselves). Checked when a key is first needed,
    # so the server can start without keys as long as no level 2 or 3 data is handled.
    vanta_key_level2_path: Path | None = None
    vanta_key_level3_path: Path | None = None

    # Device authentication (see docs/SIGNATUR.md).
    # Allowed difference between the request timestamp and the server clock.
    vanta_auth_tolerance_seconds: int = Field(default=60, ge=1, le=600)
    # Lifetime of a one-time registration code.
    vanta_registration_code_ttl_seconds: int = Field(default=600, ge=60, le=86400)

    # Self monitoring. The backup job touches this file after each successful backup.
    vanta_backup_marker_path: Path | None = None

    # Backup (see docs/BACKUP.md). The key file is a passphrase and must not live next
    # to the backups.
    vanta_backup_dir: Path | None = None
    vanta_backup_key_path: Path | None = None
    vanta_backup_keep: int = Field(default=14, ge=1)
    # Optional override of the dump command (e.g. "docker compose ... exec -T db pg_dump ...").
    vanta_backup_dump_command: str = ""
    # Uptime Kuma push URLs (secret tokens inside). Empty means no push for that source.
    kuma_push_ingest_health: SecretStr | None = None
    kuma_push_ingest_mail: SecretStr | None = None
    kuma_push_ingest_calendar: SecretStr | None = None
    kuma_push_ingest_news: SecretStr | None = None

    @property
    def kuma_push_urls(self) -> dict[str, str]:
        """Push URL per source key; only sources with a configured URL appear."""
        candidates = {
            "health": self.kuma_push_ingest_health,
            "mail": self.kuma_push_ingest_mail,
            "calendar": self.kuma_push_ingest_calendar,
            "news": self.kuma_push_ingest_news,
        }
        return {
            key: value.get_secret_value()
            for key, value in candidates.items()
            if value is not None and value.get_secret_value()
        }

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy URL for the application and migrations."""
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    """Load settings once per process."""
    return Settings()

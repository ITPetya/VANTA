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

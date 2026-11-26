import pytest
from pydantic import ValidationError

from server.config import Settings


def test_password_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_empty_password_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, postgres_password="")


def test_database_url_escapes_password() -> None:
    settings = Settings(_env_file=None, postgres_password="p@ss/word")
    assert "p%40ss%2Fword" in settings.database_url
    assert settings.database_url.startswith("postgresql+asyncpg://vanta:")

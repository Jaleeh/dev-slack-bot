import pytest
from pydantic import ValidationError

from app.config.settings import Settings


def test_startup_fails_naming_database_url_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)

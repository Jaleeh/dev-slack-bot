import pytest

from tests.support import ensure_database_exists


def test_ensure_database_exists_rejects_a_url_without_a_database_name() -> None:
    with pytest.raises(ValueError, match="database name"):
        ensure_database_exists("postgresql+psycopg://devbot:devbot@localhost:5432")

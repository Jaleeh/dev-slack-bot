from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def test_baseline_upgrades_and_downgrades_cleanly(test_database_url: str) -> None:
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", test_database_url)

    command.upgrade(config, "head")
    assert (
        current_revision(test_database_url)
        == ScriptDirectory.from_config(config).get_current_head()
    )

    command.downgrade(config, "base")
    assert current_revision(test_database_url) is None


def current_revision(database_url: str) -> str | None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import NullPool

# Short, so a health check fails fast instead of hanging the page.
DB_CONNECT_TIMEOUT_SECONDS = 2


def make_engine(database_url: str) -> Engine:
    # NullPool opens a fresh connection per use, so connect_timeout also covers a
    # database that freezes after a good check. Revisit when real queries need pooling.
    return create_engine(
        database_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
    )


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine

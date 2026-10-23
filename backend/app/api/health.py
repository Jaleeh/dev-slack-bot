import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from app.db.session import get_engine

# Covers a database that accepts the connection and then stalls mid-query,
# which the driver's connect timeout cannot catch.
HEALTH_CHECK_TIMEOUT_SECONDS = 3

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health(engine: Annotated[Engine, Depends(get_engine)]) -> JSONResponse:
    if await is_database_reachable_in_time(engine):
        return JSONResponse({"status": "ok", "database": "ok"})

    return JSONResponse({"status": "degraded", "database": "down"}, status_code=503)


async def is_database_reachable_in_time(engine: Engine) -> bool:
    try:
        return await asyncio.wait_for(
            run_in_threadpool(is_database_reachable, engine), HEALTH_CHECK_TIMEOUT_SECONDS
        )
    except TimeoutError:
        # The worker thread stays blocked until the database answers or drops the socket.
        logger.warning("Database health check timed out")
        return False


def is_database_reachable(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as error:
        # The class name only: the message can contain the connection URL.
        logger.warning("Database health check failed: %s", type(error).__name__)
        return False

    return True

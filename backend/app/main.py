import logging
from collections.abc import Awaitable, Callable, Mapping

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.config.settings import Settings
from app.db.session import make_engine

logger = logging.getLogger(__name__)

# 'unsafe-inline' is needed because the Next.js static export inlines its
# bootstrap scripts. Tighten to hashes once admin login handles secrets.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
)

SECURITY_HEADERS: Mapping[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
}


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="dev-slack-bot")
    app.state.engine = make_engine(settings.database_url)
    app.middleware("http")(add_security_headers)
    app.include_router(health_router, prefix="/api")
    app.add_api_route("/api/{path:path}", api_not_found, include_in_schema=False)
    mount_frontend(app, settings)
    return app


async def add_security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    return response


def api_not_found() -> None:
    raise HTTPException(status_code=404)


def mount_frontend(app: FastAPI, settings: Settings) -> None:
    # Mounted last so it never shadows /api routes.
    if not settings.frontend_dir.is_dir():
        logger.warning("Frontend not found at %s; serving /api only", settings.frontend_dir)
        return

    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")


def app_factory() -> FastAPI:
    """Builds the app from environment settings, for `uvicorn --factory`."""
    return create_app(Settings())

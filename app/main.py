import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.errors import error_response, install_error_handlers
from app.models.session import get_session_factory
from app.services.bootstrap import bootstrap
from app.settings.config import get_settings
from app.settings.logging import configure_logging
from app.settings.security import new_request_id
from app.views import (
    auth,
    calendar,
    catalog,
    episode,
    following,
    health,
    news,
    push,
    series,
    sync,
    user_settings,
)

logger = logging.getLogger("app.access")
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    with get_session_factory()() as db:
        bootstrap(db, settings)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Watchly API",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    install_error_handlers(app)

    allowed = {o.rstrip("/") for o in settings.allowed_origins}

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or new_request_id()
        request.state.request_id = request_id
        # Difesa CSRF oltre ai cookie SameSite: mutazioni da origini non ammesse rifiutate.
        origin = request.headers.get("origin")
        if request.method in UNSAFE_METHODS and origin and origin.rstrip("/") not in allowed:
            host = urlparse(origin).netloc
            if host != request.headers.get("host"):
                return error_response(request, 403, "forbidden_origin", "Origine non ammessa")
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allowed),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID", "X-Requested-With", "DNT"],
    )

    app.include_router(health.router)
    for module in (
        auth,
        catalog,
        series,
        following,
        calendar,
        episode,
        news,
        user_settings,
        push,
        sync,
    ):
        app.include_router(module.router, prefix="/api/v1")
    return app


app = create_app()

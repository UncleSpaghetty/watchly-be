import logging
import threading
import time
from urllib.parse import urlparse

from flask import Flask, g, request
from flask.wrappers import Response
from werkzeug.middleware.proxy_fix import ProxyFix

from app import models as _models  # noqa: F401 - registra i modelli nei metadata dflango
from app.errors import ApiError, install_error_handlers
from app.models.session import get_session
from app.routes import WatchlyRoutes
from app.services.bootstrap import bootstrap
from app.settings.config import get_settings
from app.settings.logging import WatchlyLogger
from app.settings.security import new_request_id
from dflango import DFlango

logger = logging.getLogger("app.access")
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> Flask:
    settings = get_settings()
    app = Flask(__name__)
    app.config.update(settings.flask_config())
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]

    dflango = DFlango()
    dflango.init_app(app, app.config, route=WatchlyRoutes, logger=WatchlyLogger)
    logging.getLogger().setLevel(settings.log_level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)
    install_error_handlers(app)

    allowed = {origin.rstrip("/") for origin in settings.allowed_origins}
    bootstrap_lock = threading.Lock()
    bootstrapped = False

    @app.before_request
    def request_context() -> None:
        nonlocal bootstrapped
        g.request_id = request.headers.get("x-request-id") or new_request_id()
        g.request_started = time.perf_counter()
        origin = request.headers.get("origin")
        if request.method in UNSAFE_METHODS and origin and origin.rstrip("/") not in allowed:
            if urlparse(origin).netloc != request.host:
                raise ApiError(403, "forbidden_origin", "Origine non ammessa")
        if not bootstrapped:
            with bootstrap_lock:
                if not bootstrapped:
                    bootstrap(get_session(), settings)
                    bootstrapped = True

    @app.after_request
    def response_context(response: Response) -> Response:
        response.headers["X-Request-ID"] = getattr(g, "request_id", new_request_id())
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers.setdefault("Cache-Control", "no-store")
        logger.info(
            "request",
            extra={
                "request_id": getattr(g, "request_id", None),
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": round(
                    (time.perf_counter() - getattr(g, "request_started", time.perf_counter()))
                    * 1000,
                    1,
                ),
            },
        )
        return response

    return app


app = create_app()

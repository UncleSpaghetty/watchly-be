import logging
from collections.abc import Mapping
from typing import Any

from flask import Flask, Response, g, jsonify
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException

CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = dict(headers or {})


def error_response(
    status: int,
    code: str,
    message: str,
    details: Any = None,
    headers: Mapping[str, str] | None = None,
) -> Response:
    response = jsonify(
        code=code,
        message=message,
        details=details,
        request_id=getattr(g, "request_id", None),
    )
    response.status_code = status
    response.headers.update(headers or {})
    return response


def install_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api(exc: ApiError) -> Response:
        return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.errorhandler(ValidationError)
    def _validation(exc: ValidationError) -> Response:
        return error_response(422, "validation_error", "Richiesta non valida", exc.messages)

    @app.errorhandler(HTTPException)
    def _http(exc: HTTPException) -> Response:
        return error_response(
            exc.code or 500,
            CODES.get(exc.code or 500, "error"),
            exc.description or "Errore HTTP",
        )

    @app.errorhandler(Exception)
    def _unhandled(exc: Exception) -> Response:
        logging.getLogger(__name__).exception("unhandled error")
        return error_response(500, "internal_error", "Errore interno")

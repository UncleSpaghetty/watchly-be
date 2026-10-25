import json
import logging
from datetime import UTC, datetime

from dflango.logging import Logger


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)


class WatchlyLogger(Logger):
    """Adapter del logger dflango al formato JSON già usato da Watchly."""

    def get_stdout_level(self) -> int:
        return logging.INFO

    def get_stdout_formatter(self) -> logging.Formatter:
        return JsonFormatter()

    def get_stderr_formatter(self) -> logging.Formatter:
        return JsonFormatter()

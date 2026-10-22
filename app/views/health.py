from fastapi import APIRouter
from sqlalchemy import text

from app.errors import ApiError
from app.models.session import get_session_factory

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict[str, str]:
    try:
        with get_session_factory()() as session:
            session.execute(text("SELECT 1"))
    except Exception as exc:
        raise ApiError(503, "not_ready", "Database non raggiungibile") from exc
    return {"status": "ok"}

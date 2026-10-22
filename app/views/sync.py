from uuid import UUID

from fastapi import APIRouter, Depends

from app.errors import ApiError
from app.models.sync_run import SyncRun
from app.schemas.sync import SyncRunRead
from app.services.sync import active_run, cooldown_remaining, enqueue_run
from app.settings.config import get_settings
from app.settings.security import CurrentUser, Db, RateLimiter

router = APIRouter(tags=["sync"])
sync_limit = RateLimiter(limit=20, window_seconds=300, scope="sync")


@router.post(
    "/me/sync", response_model=SyncRunRead, status_code=202, dependencies=[Depends(sync_limit)]
)
def request_sync(user: CurrentUser, db: Db) -> SyncRunRead:
    existing = active_run(db, kind="user", user_id=user.id)
    if existing:
        return SyncRunRead.model_validate(existing)
    wait = cooldown_remaining(db, user.id, get_settings().sync_cooldown_seconds)
    if wait > 0:
        raise ApiError(
            429,
            "sync_cooldown",
            "Aggiornamento richiesto troppo di recente",
            {"retry_after": wait},
            headers={"Retry-After": str(wait)},
        )
    return SyncRunRead.model_validate(enqueue_run(db, "user", user_id=user.id))


@router.get("/jobs/{job_id}", response_model=SyncRunRead)
def get_job(job_id: UUID, user: CurrentUser, db: Db) -> SyncRun:
    run = db.get(SyncRun, job_id)
    if run is None or run.user_id != user.id:
        raise ApiError(404, "job_not_found", "Job non trovato")
    return run

from typing import Any
from uuid import UUID

from app.errors import ApiError
from app.models.sync_run import SyncRun
from app.schemas.sync import SyncRunRead
from app.services.sync import active_run, cooldown_remaining, enqueue_run
from app.settings.config import get_settings
from app.settings.security import RateLimiter
from app.views.base import WatchlyView

sync_limit = RateLimiter(limit=20, window_seconds=300, scope="sync")


class SyncView(WatchlyView):
    accepted_methods = ["POST"]
    rate_limiter = sync_limit

    def post(self):
        run = active_run(self.session, kind="user", user_id=self.user.id)
        if run is None:
            wait = cooldown_remaining(
                self.session, self.user.id, get_settings().sync_cooldown_seconds
            )
            if wait > 0:
                raise ApiError(
                    429,
                    "sync_cooldown",
                    "Aggiornamento richiesto troppo di recente",
                    {"retry_after": wait},
                    headers={"Retry-After": str(wait)},
                )
            run = enqueue_run(self.session, "user", user_id=self.user.id)
        return SyncRunRead().dump(run), 202


class JobView(WatchlyView):
    accepted_methods = ["GET"]

    def get(self, job_id: UUID) -> Any:
        run = self.session.get(SyncRun, job_id)
        if run is None or run.user_id != self.user.id:
            raise ApiError(404, "job_not_found", "Job non trovato")
        return SyncRunRead().dump(run)

from app.config import get_settings
from app.errors import ApiError

# Schemas
from app.schemas.sync.sync_run_read import SyncRunReadSchema

# Services
from app.services.sync import active_run, cooldown_remaining, enqueue_run

# Config
from app.settings.security import RateLimiter

# Views
from app.views.base import WatchlyView

sync_limit = RateLimiter(limit=20, window_seconds=300, scope="sync")


class SyncView(WatchlyView):
    accepted_methods = ["POST"]
    rate_limiter = sync_limit

    def post(self):
        run = active_run(self.session, kind="user", user_id=self.user.id)
        if run is None:
            wait = cooldown_remaining(
                self.session,
                self.user.id,
                get_settings().sync_cooldown_seconds,
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
        return SyncRunReadSchema().dump(run), 202

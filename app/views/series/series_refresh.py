# Built-in
from typing import Any
from uuid import UUID

# Schemas
from app.schemas.sync.sync_run_read import SyncRunReadSchema

# Services
from app.services.series import get_series_or_404
from app.services.sync import active_run, enqueue_run

# Config
from app.settings.security import RateLimiter

# Views
from app.views.base import WatchlyView

refresh_limit = RateLimiter(limit=10, window_seconds=300, scope="series-refresh")


class SeriesRefreshView(WatchlyView):
    accepted_methods = ["POST"]
    rate_limiter = refresh_limit

    def post(self, series_id: UUID) -> Any:
        series = get_series_or_404(self.session, series_id)
        run = active_run(self.session, kind="series", series_id=series.id) or enqueue_run(
            self.session,
            "series",
            user_id=self.user.id,
            series_id=series.id,
        )
        return SyncRunReadSchema().dump(run), 202

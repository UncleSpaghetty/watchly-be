# Built-in
from typing import Any
from uuid import UUID

from app.errors import ApiError

# Models
from app.models.sync_run import SyncRun

# Schemas
from app.schemas.sync.sync_run_read import SyncRunReadSchema

# Views
from app.views.base import WatchlyView


class JobView(WatchlyView):
    accepted_methods = ["GET"]

    def get(self, job_id: UUID) -> Any:
        run = self.session.get(SyncRun, job_id)
        if run is None or run.user_id != self.user.id:
            raise ApiError(404, "job_not_found", "Job non trovato")
        return SyncRunReadSchema().dump(run)

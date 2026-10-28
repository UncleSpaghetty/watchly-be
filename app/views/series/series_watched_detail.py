from typing import Any
from uuid import UUID

from app.services.progress import set_series_watched
from app.views.base import WatchlyView


class SeriesWatchedView(WatchlyView):
    accepted_methods = ["PUT", "DELETE"]

    def put(self, series_id: UUID) -> Any:
        return set_series_watched(self.session, self.user.id, series_id, True)

    def delete(self, series_id: UUID) -> Any:
        return set_series_watched(self.session, self.user.id, series_id, False)

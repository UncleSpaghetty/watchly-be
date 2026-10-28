# Built-in
from typing import Any
from uuid import UUID

# Models
from app.models.following import Following

# Services
from app.services.series import dump_series, get_series_or_404

# Views
from app.views.base import WatchlyView


class SeriesDetailView(WatchlyView):
    accepted_methods = ["GET"]

    def get(self, series_id: UUID) -> Any:
        series = get_series_or_404(self.session, series_id)
        followed = self.session.get(Following, (self.user.id, series.id)) is not None
        return dump_series(series, followed)

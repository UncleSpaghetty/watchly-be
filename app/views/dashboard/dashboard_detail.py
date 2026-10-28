# Flask
from flask import request

from app.errors import ApiError

# Schemas
from app.schemas.dashboard.dashboard_read import DashboardResponseSchema

# Services
from app.services.dashboard import build_dashboard

# Views
from app.views.base import WatchlyView

ALLOWED_PERIODS = {4, 12, 26, 52}


class DashboardView(WatchlyView):
    accepted_methods = ["GET"]

    def get(self):
        try:
            weeks = int(request.args.get("weeks", "12"))
        except ValueError as exc:
            raise ApiError(422, "validation_error", "Periodo dashboard non valido") from exc
        if weeks not in ALLOWED_PERIODS:
            raise ApiError(422, "validation_error", "Periodo dashboard non valido")
        return DashboardResponseSchema().dump(build_dashboard(self.session, self.user, weeks))

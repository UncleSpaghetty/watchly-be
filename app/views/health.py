from sqlalchemy import text

from app.errors import ApiError
from app.views.base import WatchlyView


class LiveView(WatchlyView):
    accepted_methods = ["GET"]
    authentication_required = False

    def get(self):
        return {"status": "ok"}


class ReadyView(WatchlyView):
    accepted_methods = ["GET"]
    authentication_required = False

    def get(self):
        try:
            self.session.execute(text("SELECT 1"))
        except Exception as exc:
            raise ApiError(503, "not_ready", "Database non raggiungibile") from exc
        return {"status": "ok"}

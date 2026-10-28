# Built-in
from datetime import UTC, datetime

# Flask
from flask import g, make_response

from app.config import get_settings

# Views
from app.views.base import WatchlyView


class LogoutView(WatchlyView):
    accepted_methods = ["POST"]

    def post(self):
        settings = get_settings()
        g.auth[1].revoked_at = datetime.now(UTC)
        self.session.commit()
        response = make_response("", 204)
        response.delete_cookie(
            settings.session_cookie_name,
            path="/",
            domain=settings.session_cookie_domain,
        )
        return response

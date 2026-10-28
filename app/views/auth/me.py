# Flask
from flask import make_response

from app.config import get_settings

# Schemas
from app.schemas.auth.user_read import UserReadSchema

# Views
from app.views.base import WatchlyView


class MeView(WatchlyView):
    accepted_methods = ["GET", "DELETE"]

    def get(self):
        return UserReadSchema().dump(self.user), 200

    def delete(self):
        self.session.delete(self.user)
        self.session.commit()
        settings = get_settings()
        response = make_response("", 204)
        response.delete_cookie(
            settings.session_cookie_name,
            path="/",
            domain=settings.session_cookie_domain,
        )
        return response

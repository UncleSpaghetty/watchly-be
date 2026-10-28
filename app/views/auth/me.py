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
        return "", 204

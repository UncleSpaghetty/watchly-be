# Flask
from flask import request

# Third-party
from sqlalchemy import func, select

from app.errors import ApiError

# Models
from app.models.following import Following
from app.models.series import Series

# Services
from app.services.following import read_following

# Views
from app.views.base import WatchlyView


class FollowingListView(WatchlyView):
    accepted_methods = ["GET"]

    def get(self):
        kind, query = request.args.get("kind"), request.args.get("q")
        if kind not in {None, "anime", "tv"} or (query is not None and len(query) > 100):
            raise ApiError(422, "validation_error", "Filtro following non valido")
        statement = (
            select(Following, Series)
            .join(Series, Series.id == Following.series_id)
            .where(Following.user_id == self.user.id)
            .order_by(func.lower(Series.title))
        )
        if kind:
            statement = statement.where(Series.kind == kind)
        if query:
            statement = statement.where(
                func.lower(Series.title).contains(query.strip().lower(), autoescape=True)
            )
        return {
            "items": [
                read_following(self.session, row, series)
                for row, series in self.session.execute(statement).all()
            ]
        }

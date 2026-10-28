# Built-in
from typing import cast

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
        watch_status = request.args.get("status")
        favorite = request.args.get("favorite")
        sort = request.args.get("sort", "title")
        statuses = {"in_list", "planned", "watching", "paused", "completed", "dropped"}
        if (
            kind not in {None, "anime", "tv"}
            or watch_status not in {None, *statuses}
            or favorite not in {None, "true", "false"}
            or sort not in {"title", "next_air", "backlog", "status", "recent"}
            or (query is not None and len(query) > 100)
        ):
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
        if watch_status:
            statement = statement.where(Following.watch_status == watch_status)
        if favorite is not None:
            statement = statement.where(Following.favorite.is_(favorite == "true"))
        items = [
            read_following(self.session, row, series)
            for row, series in self.session.execute(statement).all()
        ]
        if sort == "next_air":
            items.sort(
                key=lambda item: (item["next_air_date"] is None, item["next_air_date"] or "")
            )
        elif sort == "backlog":
            items.sort(
                key=lambda item: (-cast(int, item["backlog_episodes"]), str(item["series"]))
            )
        elif sort == "status":
            items.sort(key=lambda item: (str(item["watch_status"]), str(item["series"])))
        elif sort == "recent":
            items.sort(key=lambda item: str(item["status_updated_at"]), reverse=True)
        items.sort(key=lambda item: not bool(item["favorite"]))
        return {"items": items}

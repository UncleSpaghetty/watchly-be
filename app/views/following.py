from typing import Any
from uuid import UUID

from dflango.schemas import UtcDateTimeField
from flask import request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.episode import Episode
from app.models.following import Following
from app.models.series import Series
from app.schemas.following import FollowingUpdate
from app.schemas.series import dump_series
from app.services.timeutil import now_local
from app.views.base import WatchlyView, load_json


def _read(session: Session, follow: Following, series: Series) -> dict[str, object]:
    today = now_local().date()
    next_date = session.scalar(
        select(func.min(Episode.air_date)).where(
            Episode.series_id == series.id,
            Episode.air_date >= today,
        )
    )
    return {
        "series": dump_series(series, True),
        "followed_at": UtcDateTimeField().serialize("followed_at", follow),
        "notifications_enabled": follow.notifications_enabled,
        "next_air_date": next_date.isoformat() if next_date else None,
    }


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
                _read(self.session, row, series)
                for row, series in self.session.execute(statement).all()
            ]
        }


class FollowingDetailView(WatchlyView):
    accepted_methods = ["PUT", "DELETE"]

    def put(self, series_id: UUID) -> Any:
        series = self.session.get(Series, series_id)
        if series is None:
            raise ApiError(404, "series_not_found", "Serie non trovata")
        follow = self.session.get(Following, (self.user.id, series_id))
        if follow is None:
            follow = Following(user_id=self.user.id, series_id=series_id)
            self.session.add(follow)
        if request.data:
            body = load_json(FollowingUpdate(instance=follow), partial=True)
            if "notifications_enabled" in body:
                follow.notifications_enabled = body["notifications_enabled"]
        self.session.commit()
        return _read(self.session, follow, series)

    def delete(self, series_id: UUID) -> Any:
        follow = self.session.get(Following, (self.user.id, series_id))
        if follow is not None:
            self.session.delete(follow)
            self.session.commit()
        return "", 204

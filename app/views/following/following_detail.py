# Built-in
from typing import Any
from uuid import UUID

# Flask
from flask import request

from app.errors import ApiError

# Models
from app.models.following import Following
from app.models.series import Series

# Schemas
from app.schemas.following.following_update import FollowingUpdateSchema

# Services
from app.services.following import read_following

# Views
from app.views.base import WatchlyView, load_json


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
            body = load_json(FollowingUpdateSchema(instance=follow), partial=True)
            if "notifications_enabled" in body:
                follow.notifications_enabled = body["notifications_enabled"]
        self.session.commit()
        return read_following(self.session, follow, series)

    def delete(self, series_id: UUID) -> Any:
        follow = self.session.get(Following, (self.user.id, series_id))
        if follow is not None:
            self.session.delete(follow)
            self.session.commit()
        return "", 204

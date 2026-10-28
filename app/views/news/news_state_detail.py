from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from marshmallow import Schema, fields

from app.errors import ApiError
from app.models.news_article import NewsArticle
from app.models.user_news_state import UserNewsState
from app.views.base import WatchlyView, load_json


class NewsStateUpdateSchema(Schema):
    saved = fields.Boolean()
    read = fields.Boolean()


class NewsStateView(WatchlyView):
    accepted_methods = ["PATCH"]

    def put(self, news_id: UUID) -> Any:
        if self.session.get(NewsArticle, news_id) is None:
            raise ApiError(404, "news_not_found", "Notizia non trovata")
        body = load_json(NewsStateUpdateSchema(), partial=True)
        state = self.session.get(UserNewsState, (self.user.id, news_id))
        if state is None:
            state = UserNewsState(user_id=self.user.id, news_id=news_id, saved=False)
            self.session.add(state)
        if "saved" in body:
            state.saved = body["saved"]
        if "read" in body:
            state.read_at = datetime.now(UTC) if body["read"] else None
        self.session.commit()
        return {
            "news_id": str(news_id),
            "saved": state.saved,
            "read_at": state.read_at.isoformat() if state.read_at else None,
        }

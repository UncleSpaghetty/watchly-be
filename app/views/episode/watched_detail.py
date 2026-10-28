# Built-in
from typing import Any
from uuid import UUID

# Schemas
from app.schemas.episode.watched_read import WatchedReadSchema

# Services
from app.services.progress import set_episode_watched

# Views
from app.views.base import WatchlyView


class WatchedView(WatchlyView):
    accepted_methods = ["PUT", "DELETE"]

    def put(self, episode_id: UUID) -> Any:
        row = set_episode_watched(self.session, self.user.id, episode_id, True)
        return WatchedReadSchema().dump(
            {
                "episode_id": episode_id,
                "watched": True,
                "watched_at": row.watched_at if row else None,
            }
        )

    def delete(self, episode_id: UUID) -> Any:
        set_episode_watched(self.session, self.user.id, episode_id, False)
        return WatchedReadSchema().dump(
            {"episode_id": episode_id, "watched": False, "watched_at": None}
        )

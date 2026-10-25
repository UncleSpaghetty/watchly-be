from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.errors import ApiError
from app.models.episode import Episode
from app.models.watched_episode import WatchedEpisode
from app.schemas.episode import WatchedRead
from app.views.base import WatchlyView


class WatchedView(WatchlyView):
    accepted_methods = ["PUT", "DELETE"]

    def _ensure_episode(self, episode_id: UUID) -> None:
        if self.session.get(Episode, episode_id) is None:
            raise ApiError(404, "episode_not_found", "Episodio non trovato")

    def put(self, episode_id: UUID) -> Any:
        self._ensure_episode(episode_id)
        row = self.session.get(WatchedEpisode, (self.user.id, episode_id))
        if row is None:
            row = WatchedEpisode(
                user_id=self.user.id, episode_id=episode_id, watched_at=datetime.now(UTC)
            )
            self.session.add(row)
            self.session.commit()
        return WatchedRead().dump(
            {"episode_id": episode_id, "watched": True, "watched_at": row.watched_at}
        )

    def delete(self, episode_id: UUID) -> Any:
        self._ensure_episode(episode_id)
        row = self.session.get(WatchedEpisode, (self.user.id, episode_id))
        if row is not None:
            self.session.delete(row)
            self.session.commit()
        return WatchedRead().dump({"episode_id": episode_id, "watched": False, "watched_at": None})

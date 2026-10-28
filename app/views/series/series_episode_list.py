# Built-in
from typing import Any
from uuid import UUID

# Third-party
from sqlalchemy import select

# Models
from app.models.episode import Episode
from app.models.watched_episode import WatchedEpisode

# Schemas
from app.schemas.episode.episode_read import EpisodeReadSchema

# Services
from app.services.series import dump_series, get_series_or_404

# Views
from app.views.base import WatchlyView


class SeriesEpisodesView(WatchlyView):
    accepted_methods = ["GET"]

    def get(self, series_id: UUID) -> Any:
        series = get_series_or_404(self.session, series_id)
        episodes = self.session.scalars(
            select(Episode)
            .where(Episode.series_id == series.id)
            .order_by(Episode.season_number, Episode.episode_number, Episode.air_date)
        ).all()
        ids = [episode.id for episode in episodes]
        watched = set(
            self.session.scalars(
                select(WatchedEpisode.episode_id).where(
                    WatchedEpisode.user_id == self.user.id,
                    WatchedEpisode.episode_id.in_(ids),
                )
            ).all()
        )
        data = dump_series(series)
        items = [
            EpisodeReadSchema().dump(
                {
                    "id": episode.id,
                    "series_id": episode.series_id,
                    "season_number": episode.season_number,
                    "episode_number": episode.episode_number,
                    "title": episode.title,
                    "air_at": episode.air_at,
                    "air_date": episode.air_date,
                    "source": episode.source,
                    "watched": episode.id in watched,
                }
            )
            for episode in episodes
        ]
        return {
            "episodes": items,
            "last_synced_at": data["last_synced_at"],
            "sync_status": series.last_sync_status,
            "stale": data["stale"],
        }

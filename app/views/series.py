from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.errors import ApiError
from app.models.episode import Episode
from app.models.following import Following
from app.models.series import Series
from app.models.watched_episode import WatchedEpisode
from app.schemas.episode import EpisodeRead
from app.schemas.series import dump_series
from app.schemas.sync import SyncRunRead
from app.services.sync import active_run, enqueue_run
from app.settings.security import RateLimiter
from app.views.base import WatchlyView

refresh_limit = RateLimiter(limit=10, window_seconds=300, scope="series-refresh")


class SeriesDetailView(WatchlyView):
    accepted_methods = ["GET"]

    def get(self, series_id: UUID) -> Any:
        series = self._series(series_id)
        followed = self.session.get(Following, (self.user.id, series.id)) is not None
        return dump_series(series, followed)

    def _series(self, series_id: UUID) -> Series:
        series = self.session.get(Series, series_id)
        if series is None:
            raise ApiError(404, "series_not_found", "Serie non trovata")
        return series


class SeriesEpisodesView(SeriesDetailView):
    def get(self, series_id: UUID) -> Any:
        series = self._series(series_id)
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
            EpisodeRead().dump(
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


class SeriesRefreshView(SeriesDetailView):
    accepted_methods = ["POST"]
    rate_limiter = refresh_limit

    def post(self, series_id: UUID) -> Any:
        series = self._series(series_id)
        run = active_run(self.session, kind="series", series_id=series.id) or enqueue_run(
            self.session, "series", user_id=self.user.id, series_id=series.id
        )
        return SyncRunRead().dump(run), 202

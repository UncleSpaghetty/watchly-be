import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.errors import ApiError
from app.models.episode import Episode
from app.models.following import Following
from app.models.series import Series
from app.models.watched_episode import WatchedEpisode
from app.schemas.episode import AvailabilityRead, EpisodeListResponse, EpisodeRead
from app.schemas.series import SeriesRead
from app.schemas.sync import SyncRunRead
from app.services.calendar import load_availability
from app.services.sync import active_run, enqueue_run
from app.settings.security import CurrentUser, Db, RateLimiter

router = APIRouter(prefix="/series", tags=["series"])
refresh_limit = RateLimiter(limit=10, window_seconds=300, scope="series-refresh")


def get_series_or_404(db: Db, series_id: uuid.UUID) -> Series:
    series = db.get(Series, series_id)
    if series is None:
        raise ApiError(404, "series_not_found", "Serie non trovata")
    return series


Found = Annotated[Series, Depends(get_series_or_404)]


@router.get("/{series_id}", response_model=SeriesRead)
def get_series(series: Found, user: CurrentUser, db: Db) -> SeriesRead:
    followed = db.get(Following, (user.id, series.id)) is not None
    return SeriesRead.from_model(series, followed)


@router.get("/{series_id}/episodes", response_model=EpisodeListResponse)
def list_episodes(series: Found, user: CurrentUser, db: Db) -> EpisodeListResponse:
    episodes = db.scalars(
        select(Episode)
        .where(Episode.series_id == series.id)
        .order_by(Episode.season_number, Episode.episode_number, Episode.original_air_date)
    ).all()
    ids = [e.id for e in episodes]
    availability = load_availability(db, ids)
    watched = set(
        db.scalars(
            select(WatchedEpisode.episode_id).where(
                WatchedEpisode.user_id == user.id, WatchedEpisode.episode_id.in_(ids)
            )
        ).all()
    )
    read = SeriesRead.from_model(series)
    return EpisodeListResponse(
        episodes=[
            EpisodeRead(
                id=e.id,
                series_id=e.series_id,
                season_number=e.season_number,
                episode_number=e.episode_number,
                title=e.title,
                original_air_at=e.original_air_at,
                original_air_date=e.original_air_date,
                italy=AvailabilityRead(**vars(availability[e.id])),
                watched=e.id in watched,
            )
            for e in episodes
        ],
        last_synced_at=series.last_synced_at,
        sync_status=series.last_sync_status,
        stale=read.stale,
    )


@router.post(
    "/{series_id}/refresh",
    response_model=SyncRunRead,
    status_code=202,
    dependencies=[Depends(refresh_limit)],
)
def refresh_series(series: Found, user: CurrentUser, db: Db) -> SyncRunRead:
    run = active_run(db, kind="series", series_id=series.id) or enqueue_run(
        db, "series", user_id=user.id, series_id=series.id
    )
    return SyncRunRead.model_validate(run)

from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.episode import Episode
from app.models.following import Following
from app.models.watched_episode import WatchedEpisode
from app.services.timeutil import now_local


class _RowCount(Protocol):
    rowcount: int


def episode_is_future(episode: Episode, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if episode.air_at is not None:
        air_at = episode.air_at
        if air_at.tzinfo is None:
            air_at = air_at.replace(tzinfo=UTC)
        return air_at > current
    return episode.air_date is not None and episode.air_date > now_local().date()


def set_episode_watched(
    db: Session, user_id: UUID, episode_id: UUID, watched: bool
) -> WatchedEpisode | None:
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise ApiError(404, "episode_not_found", "Episodio non trovato")
    row = db.get(WatchedEpisode, (user_id, episode_id))
    if watched:
        if episode_is_future(episode):
            raise ApiError(
                409,
                "episode_not_released",
                "Non puoi segnare come visto un episodio non ancora uscito",
            )
        if row is None:
            row = WatchedEpisode(
                user_id=user_id, episode_id=episode_id, watched_at=datetime.now(UTC)
            )
            db.add(row)
    elif row is not None:
        db.delete(row)
        row = None
    db.commit()
    return row


def set_series_watched(
    db: Session, user_id: UUID, series_id: UUID, watched: bool
) -> dict[str, int]:
    if db.get(Following, (user_id, series_id)) is None:
        raise ApiError(404, "following_not_found", "Serie non presente nella watchlist")
    if not watched:
        result = db.execute(
            delete(WatchedEpisode).where(
                WatchedEpisode.user_id == user_id,
                WatchedEpisode.episode_id.in_(
                    select(Episode.id).where(Episode.series_id == series_id)
                ),
            )
        )
        db.commit()
        deleted = cast(_RowCount, result).rowcount
        return {"updated": int(deleted or 0), "eligible": 0, "skipped_future": 0}

    now = datetime.now(UTC)
    today = now_local().date()
    eligible = list(
        db.scalars(
            select(Episode).where(
                Episode.series_id == series_id,
                or_(
                    Episode.air_at <= now,
                    and_(
                        Episode.air_at.is_(None),
                        Episode.air_date.is_not(None),
                        Episode.air_date <= today,
                    ),
                ),
            )
        ).all()
    )
    existing = set(
        db.scalars(
            select(WatchedEpisode.episode_id).where(
                WatchedEpisode.user_id == user_id,
                WatchedEpisode.episode_id.in_([episode.id for episode in eligible]),
            )
        ).all()
    )
    for episode in eligible:
        if episode.id not in existing:
            db.add(
                WatchedEpisode(
                    user_id=user_id,
                    episode_id=episode.id,
                    watched_at=now,
                )
            )
    total = (
        db.scalar(select(func.count()).select_from(Episode).where(Episode.series_id == series_id))
        or 0
    )
    db.commit()
    return {
        "updated": len(eligible) - len(existing),
        "eligible": len(eligible),
        "skipped_future": max(0, int(total) - len(eligible)),
    }

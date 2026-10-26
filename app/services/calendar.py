import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.episode import Episode
from app.models.following import Following
from app.models.series import Series
from app.models.watched_episode import WatchedEpisode

MAX_RANGE_DAYS = 100


@dataclass
class CalendarEntry:
    episode: Episode
    series: Series
    watched: bool
    air_date: date


def build_calendar(
    db: Session,
    user_id: uuid.UUID,
    start: date,
    end: date,
    *,
    kind: str | None = None,
    watched: bool | None = None,
) -> list[CalendarEntry]:
    """Episodi seguiti la cui data fornita dal provider cade nell'intervallo."""
    followed = select(Following.series_id).where(Following.user_id == user_id)
    stmt = (
        select(Episode, Series)
        .join(Series, Series.id == Episode.series_id)
        .where(
            Episode.series_id.in_(followed),
            Episode.air_date.between(start, end),
        )
    )
    if kind:
        stmt = stmt.where(Series.kind == kind)
    pairs = db.execute(stmt).all()

    watched_ids = set(
        db.scalars(
            select(WatchedEpisode.episode_id).where(
                WatchedEpisode.user_id == user_id,
                WatchedEpisode.episode_id.in_([ep.id for ep, _ in pairs]),
            )
        ).all()
    )

    entries: list[CalendarEntry] = []
    for episode, series in pairs:
        if episode.air_date is None:
            continue
        is_watched = episode.id in watched_ids
        if watched is not None and is_watched != watched:
            continue
        entries.append(CalendarEntry(episode, series, is_watched, episode.air_date))
    entries.sort(
        key=lambda entry: (
            entry.air_date,
            entry.series.title.casefold(),
            entry.episode.season_number or 0,
            entry.episode.episode_number or 0,
        )
    )
    return entries

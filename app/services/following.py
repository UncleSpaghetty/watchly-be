# dFlango
from dflango.schemas import UtcDateTimeField

# Third-party
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# Models
from app.models.episode import Episode
from app.models.following import Following
from app.models.series import Series
from app.models.watched_episode import WatchedEpisode

# Services
from app.services.series import dump_series
from app.services.timeutil import now_local


def read_following(session: Session, follow: Following, series: Series) -> dict[str, object]:
    today = now_local().date()
    next_date = session.scalar(
        select(func.min(Episode.air_date)).where(
            Episode.series_id == series.id,
            Episode.air_date >= today,
        )
    )
    aired_ids = list(
        session.scalars(
            select(Episode.id).where(
                Episode.series_id == series.id,
                Episode.air_date.is_not(None),
                Episode.air_date <= today,
            )
        ).all()
    )
    watched_ids = set(
        session.scalars(
            select(WatchedEpisode.episode_id).where(
                WatchedEpisode.user_id == follow.user_id,
                WatchedEpisode.episode_id.in_(aired_ids),
            )
        ).all()
    )
    next_unwatched = session.scalar(
        select(Episode.id)
        .where(
            Episode.series_id == series.id,
            Episode.air_date.is_not(None),
            Episode.air_date <= today,
            Episode.id.not_in(watched_ids),
        )
        .order_by(
            Episode.season_number.asc().nullsfirst(),
            Episode.episode_number.asc().nullsfirst(),
            Episode.air_date.asc(),
        )
        .limit(1)
    )
    return {
        "series": dump_series(series, True),
        "followed_at": UtcDateTimeField().serialize("followed_at", follow),
        "notifications_enabled": follow.notifications_enabled,
        "next_air_date": next_date.isoformat() if next_date else None,
        "watch_status": follow.watch_status,
        "favorite": follow.favorite,
        "status_updated_at": UtcDateTimeField().serialize("status_updated_at", follow),
        "aired_episodes": len(aired_ids),
        "watched_episodes": len(watched_ids),
        "backlog_episodes": len(aired_ids) - len(watched_ids),
        "next_unwatched_episode_id": str(next_unwatched) if next_unwatched else None,
    }

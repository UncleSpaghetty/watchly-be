# dFlango
from dflango.schemas import UtcDateTimeField

# Third-party
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# Models
from app.models.episode import Episode
from app.models.following import Following
from app.models.series import Series

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
    return {
        "series": dump_series(series, True),
        "followed_at": UtcDateTimeField().serialize("followed_at", follow),
        "notifications_enabled": follow.notifications_enabled,
        "next_air_date": next_date.isoformat() if next_date else None,
    }

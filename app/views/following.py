from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Query
from sqlalchemy import func, select

from app.errors import ApiError
from app.models.episode import Episode
from app.models.episode_availability import EpisodeAvailability
from app.models.following import Following
from app.models.series import Series
from app.schemas.following import FollowingList, FollowingRead, FollowingUpdate
from app.schemas.series import SeriesRead
from app.services.calendar import load_availability
from app.services.timeutil import now_local
from app.settings.security import CurrentUser, Db

router = APIRouter(prefix="/me/following", tags=["following"])


def _read(db: Db, follow: Following, series: Series) -> FollowingRead:
    """Prossima data italiana solo se verificata (conferma valida); altrimenti nessuna."""
    today = now_local().date()
    candidates = db.scalars(
        select(EpisodeAvailability.episode_id)
        .join(Episode, Episode.id == EpisodeAvailability.episode_id)
        .where(
            Episode.series_id == series.id,
            EpisodeAvailability.status == "confirmed",
            EpisodeAvailability.available_local_date >= today,
        )
    ).all()
    dates = [
        a.local_date
        for a in load_availability(db, list(set(candidates))).values()
        if a.status == "confirmed" and a.local_date and a.local_date >= today
    ]
    return FollowingRead(
        series=SeriesRead.from_model(series, True),
        followed_at=follow.followed_at,
        notifications_enabled=follow.notifications_enabled,
        next_italy_date=min(dates) if dates else None,
    )


@router.get("", response_model=FollowingList)
def list_following(
    user: CurrentUser,
    db: Db,
    kind: Annotated[str | None, Query(pattern="^(anime|tv)$")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> FollowingList:
    stmt = (
        select(Following, Series)
        .join(Series, Series.id == Following.series_id)
        .where(Following.user_id == user.id)
        .order_by(func.lower(Series.title))
    )
    if kind:
        stmt = stmt.where(Series.kind == kind)
    if q:
        stmt = stmt.where(func.lower(Series.title).contains(q.strip().lower(), autoescape=True))
    return FollowingList(items=[_read(db, f, s) for f, s in db.execute(stmt).all()])


@router.put("/{series_id}", response_model=FollowingRead)
def follow(
    series_id: UUID,
    user: CurrentUser,
    db: Db,
    body: Annotated[FollowingUpdate | None, Body()] = None,
) -> FollowingRead:
    series = db.get(Series, series_id)
    if series is None:
        raise ApiError(404, "series_not_found", "Serie non trovata")
    follow_row = db.get(Following, (user.id, series_id))
    if follow_row is None:
        follow_row = Following(user_id=user.id, series_id=series_id)
        db.add(follow_row)
    if body is not None and "notifications_enabled" in body.model_fields_set:
        follow_row.notifications_enabled = body.notifications_enabled
    db.commit()
    return _read(db, follow_row, series)


@router.delete("/{series_id}", status_code=204)
def unfollow(series_id: UUID, user: CurrentUser, db: Db) -> None:
    follow_row = db.get(Following, (user.id, series_id))
    if follow_row is not None:
        db.delete(follow_row)
        db.commit()

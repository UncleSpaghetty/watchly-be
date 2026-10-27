import uuid
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.episode import Episode
from app.models.following import Following
from app.models.series import Series
from app.models.user import User
from app.models.watched_episode import WatchedEpisode
from app.services.timeutil import get_zone


def _percentage(value: int, total: int) -> int:
    return round(value * 100 / total) if total else 0


def _runtime(episode: Episode, series: Series) -> int | None:
    return episode.duration_minutes or series.episode_runtime_minutes


def build_dashboard(
    db: Session,
    user: User,
    weeks: int,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    timezone = get_zone(user.timezone)
    today = generated_at.astimezone(timezone).date()
    current_week = today - timedelta(days=today.weekday())
    first_week = current_week - timedelta(weeks=weeks - 1)

    followed_series = db.scalars(
        select(Series)
        .join(Following, Following.series_id == Series.id)
        .where(Following.user_id == user.id)
    ).all()
    followed_ids = [series.id for series in followed_series]

    watched_rows = db.execute(
        select(WatchedEpisode, Episode, Series)
        .join(Episode, Episode.id == WatchedEpisode.episode_id)
        .join(Series, Series.id == Episode.series_id)
        .where(WatchedEpisode.user_id == user.id)
    ).all()

    aired_rows = (
        db.execute(
            select(Episode, Series, WatchedEpisode.watched_at)
            .join(Series, Series.id == Episode.series_id)
            .outerjoin(
                WatchedEpisode,
                and_(
                    WatchedEpisode.episode_id == Episode.id,
                    WatchedEpisode.user_id == user.id,
                ),
            )
            .where(Episode.series_id.in_(followed_ids), Episode.air_date <= today)
        ).all()
        if followed_ids
        else []
    )

    watched_total = len(watched_rows)
    known_runtime = [
        runtime
        for _, episode, series in watched_rows
        if (runtime := _runtime(episode, series)) is not None
    ]
    estimated_minutes = sum(known_runtime)
    watched_current = sum(1 for _, _, watched_at in aired_rows if watched_at is not None)
    aired_total = len(aired_rows)

    upcoming_rows = (
        db.execute(
            select(Episode, Series)
            .join(Series, Series.id == Episode.series_id)
            .where(
                Episode.series_id.in_(followed_ids),
                Episode.air_date.between(today, today + timedelta(days=29)),
            )
        ).all()
        if followed_ids
        else []
    )

    activity = {first_week + timedelta(weeks=index): 0 for index in range(weeks)}
    active_dates: set[date] = set()
    for watched, _, _ in watched_rows:
        local_date = watched.watched_at.astimezone(timezone).date()
        active_dates.add(local_date)
        week_start = local_date - timedelta(days=local_date.weekday())
        if week_start in activity:
            activity[week_start] += 1

    cursor = today if today in active_dates else today - timedelta(days=1)
    current_streak = 0
    while cursor in active_dates:
        current_streak += 1
        cursor -= timedelta(days=1)

    longest_streak = 0
    running_streak = 0
    previous: date | None = None
    for active_date in sorted(active_dates):
        running_streak = (
            running_streak + 1
            if previous is not None and active_date == previous + timedelta(days=1)
            else 1
        )
        longest_streak = max(longest_streak, running_streak)
        previous = active_date

    progress: dict[uuid.UUID, dict[str, Any]] = {
        series.id: {
            "series_id": series.id,
            "title": series.title,
            "poster_url": series.poster_url,
            "kind": series.kind,
            "watched": 0,
            "aired": 0,
            "average_rating": series.average_rating,
        }
        for series in followed_series
    }
    for _episode, series, watched_at in aired_rows:
        item = progress[series.id]
        item["aired"] += 1
        if watched_at is not None:
            item["watched"] += 1
    for item in progress.values():
        item["percentage"] = _percentage(item["watched"], item["aired"])
        item["backlog"] = item["aired"] - item["watched"]

    genre_counts: Counter[str] = Counter()
    genre_basis = "watched_episodes"
    for _, _, series in watched_rows:
        genre_counts.update(series.genres)
    if not genre_counts:
        genre_basis = "followed_series"
        for series in followed_series:
            genre_counts.update(series.genres)

    top_series: dict[uuid.UUID, dict[str, Any]] = {}
    for _, episode, series in watched_rows:
        item = top_series.setdefault(
            series.id,
            {
                "series_id": series.id,
                "title": series.title,
                "poster_url": series.poster_url,
                "watched": 0,
                "estimated_minutes": 0,
            },
        )
        item["watched"] += 1
        item["estimated_minutes"] += _runtime(episode, series) or 0

    ratings = [
        series.average_rating for series in followed_series if series.average_rating is not None
    ]
    anime_count = sum(1 for series in followed_series if series.kind == "anime")

    return {
        "generated_at": generated_at,
        "timezone": user.timezone,
        "period_weeks": weeks,
        "kpis": {
            "followed_series": len(followed_series),
            "watched_episodes": watched_total,
            "aired_episodes": aired_total,
            "completion_percentage": _percentage(watched_current, aired_total),
            "backlog_episodes": aired_total - watched_current,
            "upcoming_7_days": sum(
                1
                for episode, _ in upcoming_rows
                if episode.air_date is not None and episode.air_date <= today + timedelta(days=6)
            ),
            "upcoming_30_days": len(upcoming_rows),
            "estimated_watch_minutes": estimated_minutes,
            "duration_coverage_percentage": _percentage(len(known_runtime), watched_total),
            "average_provider_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
            "rated_series": len(ratings),
            "current_activity_streak": current_streak,
            "longest_activity_streak": longest_streak,
        },
        "activity": [
            {"period_start": week_start, "watched_count": count}
            for week_start, count in activity.items()
        ],
        "watchlist_breakdown": {
            "anime": anime_count,
            "tv": len(followed_series) - anime_count,
        },
        "genres": {
            "basis": genre_basis,
            "items": [
                {"name": name, "count": count} for name, count in genre_counts.most_common(8)
            ],
        },
        "series_progress": sorted(
            progress.values(),
            key=lambda item: (-item["backlog"], -item["watched"], item["title"].casefold()),
        )[:8],
        "top_series": sorted(
            top_series.values(),
            key=lambda item: (-item["watched"], item["title"].casefold()),
        )[:5],
    }

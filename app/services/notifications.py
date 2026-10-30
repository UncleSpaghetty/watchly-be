import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import cast

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.episode import Episode
from app.models.episode_date_change import EpisodeDateChange
from app.models.following import Following
from app.models.news_article import NewsArticle
from app.models.news_series_link import NewsSeriesLink
from app.models.notification_delivery import NotificationDelivery
from app.models.push_subscription import PushSubscription
from app.models.series import Series
from app.models.user import User
from app.services.calendar import CalendarEntry, build_calendar
from app.services.timeutil import get_zone

logger = logging.getLogger(__name__)

CHANNEL = "webpush"
MAX_ATTEMPTS = 3
RETRY_DELAY = timedelta(minutes=5)


def build_payload(
    entries: list[CalendarEntry], target_date: str, lead_days: int = 0
) -> dict[str, str]:
    """Riepilogo giornaliero delle date pubblicate dai provider."""
    names = list(dict.fromkeys(e.series.title for e in entries))
    shown = ", ".join(names[:3]) + (f" e altri {len(names) - 3}" if len(names) > 3 else "")
    count = len(entries)
    noun = "episodio" if count == 1 else "episodi"
    when = "oggi" if lead_days == 0 else ("domani" if lead_days == 1 else f"fra {lead_days} giorni")
    return {
        "title": f"Watchly · uscite {when}",
        "body": f"{count} {noun} in programma {when}: {shown}",
        "url": f"/calendar?date={target_date}",
        "tag": f"watchly-{target_date}",
    }


def _in_quiet_hours(local_time: str, start: str | None, end: str | None) -> bool:
    if not start or not end or start == end:
        return False
    if start < end:
        return start <= local_time < end
    return local_time >= start or local_time < end


def _push(settings: Settings, sub: PushSubscription, payload: dict[str, str]) -> bool:
    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=12 * 3600,
        )
        sub.last_success_at = datetime.now(UTC)
        return True
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):  # subscription scaduta o revocata
            sub.expired_at = datetime.now(UTC)
        logger.warning("web push failed (status=%s)", status)
        return False


def _claim(
    db: Session, user: User, local_date_obj: object, channel: str = CHANNEL
) -> NotificationDelivery | None:
    """Deduplica idempotente su (user, local_date, channel); consente retry limitati."""
    delivery = db.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.user_id == user.id,
            NotificationDelivery.local_date == local_date_obj,
            NotificationDelivery.channel == channel,
        )
    )
    now = datetime.now(UTC)
    if delivery is None:
        delivery = NotificationDelivery(user_id=user.id, local_date=local_date_obj, channel=channel)
        db.add(delivery)
        try:
            db.commit()
        except IntegrityError:  # un altro worker l'ha creata
            db.rollback()
            return None
        return delivery
    if delivery.status == "sent" or delivery.attempts >= MAX_ATTEMPTS:
        return None
    if delivery.last_attempt_at and now - delivery.last_attempt_at < RETRY_DELAY:
        return None
    return cast(NotificationDelivery, delivery)


def _deliver(
    db: Session,
    settings: Settings,
    user: User,
    subscriptions: Sequence[PushSubscription],
    local_date_obj: object,
    channel: str,
    item_count: int,
    payload: dict[str, str],
    now: datetime,
) -> bool:
    delivery = _claim(db, user, local_date_obj, channel)
    if delivery is None:
        return False
    delivery.attempts += 1
    delivery.last_attempt_at = now
    delivery.episode_count = item_count
    ok = any([_push(settings, subscription, payload) for subscription in subscriptions])
    delivery.status = "sent" if ok else "failed"
    delivery.sent_at = now if ok else None
    delivery.error = None if ok else "Nessuna subscription ha accettato l'invio"
    db.commit()
    return ok


def _list_payload(title: str, names: list[str], url: str, tag: str) -> dict[str, str]:
    unique = list(dict.fromkeys(names))
    shown = ", ".join(unique[:3])
    if len(unique) > 3:
        shown += f" e altri {len(unique) - 3}"
    return {"title": title, "body": shown, "url": url, "tag": tag}


def send_due_notifications(db: Session, settings: Settings, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    if not (settings.vapid_private_key and settings.vapid_public_key):
        return 0
    sent = 0
    users = db.scalars(
        select(User).where(User.notifications_enabled.is_(True), User.is_active.is_(True))
    ).all()
    for user in users:
        local = now.astimezone(get_zone(user.timezone))
        local_time = local.strftime("%H:%M")
        if local_time < user.notification_local_time or _in_quiet_hours(
            local_time, user.notification_quiet_start, user.notification_quiet_end
        ):
            continue
        subs = db.scalars(
            select(PushSubscription).where(
                PushSubscription.user_id == user.id, PushSubscription.expired_at.is_(None)
            )
        ).all()
        if not subs:
            continue
        muted = set(
            db.scalars(
                select(Following.series_id).where(
                    Following.user_id == user.id, Following.notifications_enabled.is_(False)
                )
            ).all()
        )
        today = local.date()
        if user.notify_releases:
            target = today + timedelta(days=user.notification_lead_days)
            entries = [
                entry
                for entry in build_calendar(db, user.id, target, target)
                if entry.series.id not in muted
            ]
            if entries:
                payload = build_payload(entries, target.isoformat(), user.notification_lead_days)
                sent += int(
                    _deliver(db, settings, user, subs, today, CHANNEL, len(entries), payload, now)
                )

        since = now - timedelta(days=1)
        if user.notify_schedule_changes:
            changed_titles = list(
                db.scalars(
                    select(Series.title)
                    .join(Episode, Episode.series_id == Series.id)
                    .join(EpisodeDateChange, EpisodeDateChange.episode_id == Episode.id)
                    .join(Following, Following.series_id == Series.id)
                    .where(
                        Following.user_id == user.id,
                        Following.series_id.not_in(muted),
                        EpisodeDateChange.changed_at >= since,
                    )
                ).all()
            )
            if changed_titles:
                payload = _list_payload(
                    "Watchly · programmazione aggiornata",
                    changed_titles,
                    "/my-series",
                    f"watchly-changes-{today.isoformat()}",
                )
                sent += int(
                    _deliver(
                        db,
                        settings,
                        user,
                        subs,
                        today,
                        "webpush-changes",
                        len(changed_titles),
                        payload,
                        now,
                    )
                )

        if user.notify_new_seasons:
            season_titles = list(
                db.scalars(
                    select(Series.title)
                    .join(Episode, Episode.series_id == Series.id)
                    .join(Following, Following.series_id == Series.id)
                    .where(
                        Following.user_id == user.id,
                        Following.series_id.not_in(muted),
                        Episode.created_at >= since,
                        Episode.season_number > 1,
                        Episode.episode_number == 1,
                    )
                ).all()
            )
            if season_titles:
                payload = _list_payload(
                    "Watchly · nuove stagioni",
                    season_titles,
                    "/my-series",
                    f"watchly-seasons-{today.isoformat()}",
                )
                sent += int(
                    _deliver(
                        db,
                        settings,
                        user,
                        subs,
                        today,
                        "webpush-seasons",
                        len(season_titles),
                        payload,
                        now,
                    )
                )

        news_days = 7 if user.weekly_digest and local.weekday() == 0 else 1
        if user.notify_news or (user.weekly_digest and local.weekday() == 0):
            news_titles = list(
                db.scalars(
                    select(NewsArticle.title)
                    .join(NewsSeriesLink, NewsSeriesLink.news_id == NewsArticle.id)
                    .join(Following, Following.series_id == NewsSeriesLink.series_id)
                    .where(
                        Following.user_id == user.id,
                        Following.series_id.not_in(muted),
                        NewsArticle.published_at >= now - timedelta(days=news_days),
                    )
                    .order_by(NewsArticle.published_at.desc())
                    .limit(10)
                ).all()
            )
            if news_titles:
                digest = news_days == 7
                payload = _list_payload(
                    "Watchly · riepilogo settimanale" if digest else "Watchly · nuove notizie",
                    news_titles,
                    "/news?feed=followed",
                    f"watchly-{'digest' if digest else 'news'}-{today.isoformat()}",
                )
                sent += int(
                    _deliver(
                        db,
                        settings,
                        user,
                        subs,
                        today,
                        "webpush-digest" if digest else "webpush-news",
                        len(news_titles),
                        payload,
                        now,
                    )
                )
    return sent

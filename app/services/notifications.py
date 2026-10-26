import json
import logging
from datetime import UTC, datetime, timedelta
from typing import cast

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.following import Following
from app.models.notification_delivery import NotificationDelivery
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.calendar import CalendarEntry, build_calendar
from app.services.timeutil import get_zone
from app.settings.config import Settings

logger = logging.getLogger(__name__)

CHANNEL = "webpush"
MAX_ATTEMPTS = 3
RETRY_DELAY = timedelta(minutes=5)


def build_payload(entries: list[CalendarEntry], local_date: str) -> dict[str, str]:
    """Riepilogo giornaliero delle date pubblicate dai provider."""
    names = list(dict.fromkeys(e.series.title for e in entries))
    shown = ", ".join(names[:3]) + (f" e altri {len(names) - 3}" if len(names) > 3 else "")
    count = len(entries)
    noun = "episodio" if count == 1 else "episodi"
    return {
        "title": "Watchly · uscite di oggi",
        "body": f"{count} {noun} in programma oggi: {shown}",
        "url": f"/?date={local_date}",
        "tag": f"watchly-{local_date}",
    }


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


def _claim(db: Session, user: User, local_date_obj: object) -> NotificationDelivery | None:
    """Deduplica idempotente su (user, local_date, channel); consente retry limitati."""
    delivery = db.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.user_id == user.id,
            NotificationDelivery.local_date == local_date_obj,
            NotificationDelivery.channel == CHANNEL,
        )
    )
    now = datetime.now(UTC)
    if delivery is None:
        delivery = NotificationDelivery(user_id=user.id, local_date=local_date_obj, channel=CHANNEL)
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
        if local.strftime("%H:%M") < user.notification_local_time:
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
        entries = [
            e
            for e in build_calendar(db, user.id, today, today)
            if e.series.id not in muted
        ]
        if not entries:
            continue
        delivery = _claim(db, user, today)
        if delivery is None:
            continue
        payload = build_payload(entries, today.isoformat())
        delivery.attempts += 1
        delivery.last_attempt_at = now
        delivery.episode_count = len(entries)
        ok = any([_push(settings, sub, payload) for sub in subs])
        delivery.status = "sent" if ok else "failed"
        delivery.sent_at = now if ok else None
        delivery.error = None if ok else "Nessuna subscription ha accettato l'invio"
        db.commit()
        sent += int(ok)
    return sent

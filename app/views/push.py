from datetime import UTC, datetime

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.models.push_subscription import PushSubscription
from app.schemas.push import (
    PushSubscriptionCreate,
    PushSubscriptionDelete,
    PushSubscriptionRead,
    VapidKeyRead,
)
from app.settings.config import get_settings
from app.settings.security import CurrentUser, Db

router = APIRouter(tags=["push"])


@router.get("/push/vapid-public-key", response_model=VapidKeyRead)
def vapid_public_key() -> VapidKeyRead:
    return VapidKeyRead(public_key=get_settings().vapid_public_key)


@router.post("/me/push-subscriptions", response_model=PushSubscriptionRead, status_code=201)
def register(
    body: PushSubscriptionCreate, user: CurrentUser, db: Db, response: Response
) -> PushSubscription:
    endpoint = str(body.endpoint)
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if sub is None:
        sub = PushSubscription(user_id=user.id, endpoint=endpoint, p256dh="", auth="")
        db.add(sub)
    else:
        response.status_code = 200
    # Un endpoint appartiene a un solo utente: una nuova registrazione lo riassegna.
    sub.user_id = user.id
    sub.p256dh, sub.auth = body.keys.p256dh, body.keys.auth
    sub.expired_at = None
    sub.created_at = sub.created_at or datetime.now(UTC)
    db.commit()
    return sub


@router.delete("/me/push-subscriptions", status_code=204)
def unregister(body: PushSubscriptionDelete, user: CurrentUser, db: Db) -> None:
    sub = db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == str(body.endpoint), PushSubscription.user_id == user.id
        )
    )
    if sub is not None:
        db.delete(sub)
        db.commit()

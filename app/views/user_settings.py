from fastapi import APIRouter
from sqlalchemy import func, select

from app.models.push_subscription import PushSubscription
from app.schemas.user_settings import UserSettingsRead, UserSettingsUpdate
from app.settings.config import get_settings
from app.settings.security import CurrentUser, Db

router = APIRouter(prefix="/me/settings", tags=["settings"])


def _read(db: Db, user: CurrentUser) -> UserSettingsRead:
    settings = get_settings()
    count = db.scalar(
        select(func.count())
        .select_from(PushSubscription)
        .where(PushSubscription.user_id == user.id, PushSubscription.expired_at.is_(None))
    )
    item = UserSettingsRead.model_validate(user)
    item.push_available = bool(settings.vapid_public_key and settings.vapid_private_key)
    item.push_subscriptions = count or 0
    return item


@router.get("", response_model=UserSettingsRead)
def get_settings_view(user: CurrentUser, db: Db) -> UserSettingsRead:
    return _read(db, user)


@router.patch("", response_model=UserSettingsRead)
def update_settings(body: UserSettingsUpdate, user: CurrentUser, db: Db) -> UserSettingsRead:
    for field in body.model_fields_set:
        value = getattr(body, field)
        if value is not None:
            setattr(user, field, value)
    db.commit()
    return _read(db, user)

from sqlalchemy import func, select

from app.models.push_subscription import PushSubscription
from app.schemas.user_settings import UserSettingsRead, UserSettingsUpdate
from app.settings.config import get_settings
from app.views.base import WatchlyView, load_json


class UserSettingsView(WatchlyView):
    accepted_methods = ["GET", "PATCH"]

    def _read(self):
        settings = get_settings()
        count = self.session.scalar(
            select(func.count())
            .select_from(PushSubscription)
            .where(
                PushSubscription.user_id == self.user.id,
                PushSubscription.expired_at.is_(None),
            )
        )
        data = UserSettingsRead().dump(self.user)
        data["push_available"] = bool(settings.vapid_public_key and settings.vapid_private_key)
        data["push_subscriptions"] = count or 0
        return data

    def get(self):
        return self._read()

    def put(self):
        body = load_json(UserSettingsUpdate(instance=self.user), partial=True)
        for field, value in body.items():
            if value is not None:
                setattr(self.user, field, value)
        self.session.commit()
        return self._read()

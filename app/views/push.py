from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.models.push_subscription import PushSubscription
from app.schemas.push import (
    PushSubscriptionCreate,
    PushSubscriptionDelete,
    PushSubscriptionRead,
    VapidKeyRead,
)
from app.settings.config import get_settings
from app.views.base import WatchlyView, load_json


class VapidKeyView(WatchlyView):
    accepted_methods = ["GET"]
    authentication_required = False

    def get(self):
        return VapidKeyRead().dump({"public_key": get_settings().vapid_public_key})


class PushSubscriptionsView(WatchlyView):
    accepted_methods = ["POST", "DELETE"]

    def post(self):
        body = load_json(PushSubscriptionCreate())
        endpoint = body["endpoint"]
        subscription = self.session.scalar(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        status = 200
        if subscription is None:
            subscription = PushSubscription(
                user_id=self.user.id, endpoint=endpoint, p256dh="", auth=""
            )
            self.session.add(subscription)
            status = 201
        subscription.user_id = self.user.id
        subscription.p256dh = body["keys"]["p256dh"]
        subscription.auth = body["keys"]["auth"]
        subscription.expired_at = None
        subscription.created_at = subscription.created_at or datetime.now(UTC)
        self.session.commit()
        return PushSubscriptionRead().dump(subscription), status

    def delete(self):
        body = load_json(PushSubscriptionDelete())
        subscription = self.session.scalar(
            select(PushSubscription).where(
                PushSubscription.endpoint == body["endpoint"],
                PushSubscription.user_id == self.user.id,
            )
        )
        if subscription is not None:
            self.session.delete(subscription)
            self.session.commit()
        return "", 204


class PushSubscriptionDetailView(WatchlyView):
    accepted_methods = ["DELETE"]

    def delete(self, subscription_id: UUID) -> Any:
        subscription = self.session.get(PushSubscription, subscription_id)
        if subscription is not None and subscription.user_id == self.user.id:
            self.session.delete(subscription)
            self.session.commit()
        return "", 204

# Built-in
from datetime import UTC, datetime

# Third-party
from sqlalchemy import select

# Models
from app.models.push_subscription import PushSubscription

# Schemas
from app.schemas.push.push_subscription_create import PushSubscriptionCreateSchema
from app.schemas.push.push_subscription_delete import PushSubscriptionDeleteSchema
from app.schemas.push.push_subscription_read import PushSubscriptionReadSchema

# Views
from app.views.base import WatchlyView, load_json


class PushSubscriptionsView(WatchlyView):
    accepted_methods = ["POST", "DELETE"]

    def post(self):
        body = load_json(PushSubscriptionCreateSchema())
        endpoint = body["endpoint"]
        subscription = self.session.scalar(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        status = 200
        if subscription is None:
            subscription = PushSubscription(
                user_id=self.user.id,
                endpoint=endpoint,
                p256dh="",
                auth="",
            )
            self.session.add(subscription)
            status = 201
        subscription.user_id = self.user.id
        subscription.p256dh = body["keys"]["p256dh"]
        subscription.auth = body["keys"]["auth"]
        subscription.expired_at = None
        subscription.created_at = subscription.created_at or datetime.now(UTC)
        self.session.commit()
        return PushSubscriptionReadSchema().dump(subscription), status

    def delete(self):
        body = load_json(PushSubscriptionDeleteSchema())
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

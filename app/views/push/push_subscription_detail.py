# Built-in
from typing import Any
from uuid import UUID

# Models
from app.models.push_subscription import PushSubscription

# Views
from app.views.base import WatchlyView


class PushSubscriptionDetailView(WatchlyView):
    accepted_methods = ["DELETE"]

    def delete(self, subscription_id: UUID) -> Any:
        subscription = self.session.get(PushSubscription, subscription_id)
        if subscription is not None and subscription.user_id == self.user.id:
            self.session.delete(subscription)
            self.session.commit()
        return "", 204

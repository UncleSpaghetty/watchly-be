import unittest
from datetime import UTC, date, datetime
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.base import Base
from app.models.episode import Episode
from app.models.following import Following
from app.models.notification_delivery import NotificationDelivery
from app.models.push_subscription import PushSubscription
from app.models.series import Series
from app.models.series_external_id import SeriesExternalId
from app.models.user import User
from app.models.watched_episode import WatchedEpisode
from app.services.notifications import send_due_notifications


class NotificationPreferenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                Series.__table__,
                SeriesExternalId.__table__,
                Episode.__table__,
                Following.__table__,
                WatchedEpisode.__table__,
                PushSubscription.__table__,
                NotificationDelivery.__table__,
            ],
        )
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    @patch("app.services.notifications._push", return_value=True)
    def test_release_notification_honors_lead_time(self, mocked_push: object) -> None:
        user = User(
            email="notify@example.com",
            password_hash="!",
            notifications_enabled=True,
            notification_local_time="12:00",
            notification_lead_days=1,
            notify_releases=True,
            notify_schedule_changes=False,
            notify_new_seasons=False,
            notify_news=False,
            weekly_digest=False,
        )
        series = Series(kind="anime", title="Tomorrow", alternative_titles=[], genres=[])
        self.db.add_all([user, series])
        self.db.flush()
        self.db.add_all(
            [
                Following(user_id=user.id, series_id=series.id),
                Episode(
                    series_id=series.id,
                    source="anilist",
                    external_id="1",
                    episode_number=1,
                    air_date=date(2026, 10, 29),
                ),
                PushSubscription(
                    user_id=user.id,
                    endpoint="https://push.example/1",
                    p256dh="key",
                    auth="auth",
                ),
            ]
        )
        self.db.commit()

        settings = Settings(vapid_private_key="private", vapid_public_key="public")
        sent = send_due_notifications(
            self.db,
            settings,
            now=datetime(2026, 10, 28, 11, 0, tzinfo=UTC),
        )

        self.assertEqual(sent, 1)
        delivery = self.db.scalar(select(NotificationDelivery))
        self.assertIsNotNone(delivery)
        self.assertEqual(delivery.episode_count, 1)  # type: ignore[union-attr]
        self.assertEqual(delivery.status, "sent")  # type: ignore[union-attr]
        self.assertTrue(mocked_push)  # keeps the injected mock explicit for strict linters


if __name__ == "__main__":
    unittest.main()

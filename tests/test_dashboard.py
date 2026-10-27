import unittest
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.episode import Episode
from app.models.following import Following
from app.models.series import Series
from app.models.series_external_id import SeriesExternalId
from app.models.user import User
from app.models.watched_episode import WatchedEpisode
from app.services.dashboard import build_dashboard


class DashboardTest(unittest.TestCase):
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
            ],
        )
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_builds_personal_metrics_and_estimated_runtime(self) -> None:
        now = datetime(2026, 10, 27, 12, tzinfo=UTC)
        user = User(email="dashboard@example.com", password_hash="!", display_name="Dashboard")
        series = Series(
            kind="anime",
            title="Test Anime",
            alternative_titles=[],
            genres=["Action", "Drama"],
            average_rating=84.0,
            rating_source="anilist",
            episode_runtime_minutes=24,
        )
        self.db.add_all([user, series])
        self.db.flush()
        self.db.add(Following(user_id=user.id, series_id=series.id, followed_at=now))

        episodes = [
            Episode(
                id=uuid.uuid4(),
                series_id=series.id,
                source="anilist",
                external_id=str(index),
                episode_number=index,
                air_date=date(2026, 10, 20) + timedelta(days=index),
                duration_minutes=25 if index == 1 else None,
            )
            for index in range(1, 4)
        ]
        self.db.add_all(episodes)
        self.db.flush()
        self.db.add_all(
            [
                WatchedEpisode(
                    user_id=user.id,
                    episode_id=episodes[0].id,
                    watched_at=now - timedelta(days=1),
                ),
                WatchedEpisode(
                    user_id=user.id,
                    episode_id=episodes[1].id,
                    watched_at=now,
                ),
            ]
        )
        self.db.commit()

        result = build_dashboard(self.db, user, 4, now=now)

        self.assertEqual(result["kpis"]["followed_series"], 1)
        self.assertEqual(result["kpis"]["watched_episodes"], 2)
        self.assertEqual(result["kpis"]["estimated_watch_minutes"], 49)
        self.assertEqual(result["kpis"]["duration_coverage_percentage"], 100)
        self.assertEqual(result["kpis"]["completion_percentage"], 67)
        self.assertEqual(result["kpis"]["current_activity_streak"], 2)
        self.assertEqual(result["genres"]["items"][0]["count"], 2)
        self.assertEqual(result["series_progress"][0]["backlog"], 1)


if __name__ == "__main__":
    unittest.main()

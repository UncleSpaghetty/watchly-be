import unittest
import uuid
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.base import Base
from app.models.episode import Episode
from app.models.following import Following
from app.models.series import Series
from app.models.series_external_id import SeriesExternalId
from app.models.user import User
from app.models.watched_episode import WatchedEpisode
from app.services.progress import set_episode_watched, set_series_watched


class ProgressTest(unittest.TestCase):
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
        self.user = User(email="progress@example.com", password_hash="!")
        self.series = Series(kind="anime", title="Progress", alternative_titles=[], genres=[])
        self.db.add_all([self.user, self.series])
        self.db.flush()
        self.db.add(Following(user_id=self.user.id, series_id=self.series.id))
        self.past = Episode(
            id=uuid.uuid4(),
            series_id=self.series.id,
            source="anilist",
            external_id="1",
            episode_number=1,
            air_date=date(2020, 1, 1),
        )
        self.future = Episode(
            id=uuid.uuid4(),
            series_id=self.series.id,
            source="anilist",
            external_id="2",
            episode_number=2,
            air_date=date(2099, 1, 1),
        )
        self.db.add_all([self.past, self.future])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_future_episode_cannot_be_marked_watched(self) -> None:
        with self.assertRaises(ApiError) as caught:
            set_episode_watched(self.db, self.user.id, self.future.id, True)
        self.assertEqual(caught.exception.code, "episode_not_released")
        self.assertIsNone(self.db.get(WatchedEpisode, (self.user.id, self.future.id)))

    def test_bulk_marks_only_released_episodes_and_can_clear_all(self) -> None:
        result = set_series_watched(self.db, self.user.id, self.series.id, True)
        watched = set(
            self.db.scalars(
                select(WatchedEpisode.episode_id).where(
                    WatchedEpisode.user_id == self.user.id
                )
            ).all()
        )
        self.assertEqual(watched, {self.past.id})
        self.assertEqual(result["eligible"], 1)
        self.assertEqual(result["skipped_future"], 1)

        cleared = set_series_watched(self.db, self.user.id, self.series.id, False)
        self.assertEqual(cleared["updated"], 1)
        self.assertEqual(
            self.db.scalar(
                select(WatchedEpisode).where(WatchedEpisode.user_id == self.user.id)
            ),
            None,
        )


if __name__ == "__main__":
    unittest.main()

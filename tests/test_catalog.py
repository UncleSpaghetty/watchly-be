import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.series import Series
from app.models.series_external_id import SeriesExternalId
from app.providers.base import SearchResult
from app.services.catalog import upsert_result


class CatalogUpsertTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[Series.__table__, SeriesExternalId.__table__],
        )
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_new_series_can_merge_provider_genres_before_first_flush(self) -> None:
        series = upsert_result(
            self.db,
            SearchResult(
                source="anilist",
                external_id="1",
                title="JoJo's Bizarre Adventure",
                kind="anime",
                genres=["Action", "Adventure", "Action"],
            ),
        )

        self.assertEqual(series.genres, ["Action", "Adventure"])
        self.assertEqual(series.external_ids[0].source, "anilist")
        self.assertEqual(series.external_ids[0].external_id, "1")


if __name__ == "__main__":
    unittest.main()

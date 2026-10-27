import json
import unittest

import httpx

from app.providers.anilist import AniListProvider
from app.providers.kitsu import KitsuProvider
from app.providers.tmdb import TmdbProvider


class ProviderMetadataTest(unittest.TestCase):
    def test_anilist_normalizes_rating_genres_and_runtime(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            document = json.loads(request.content)["query"]
            media = {
                "id": 1,
                "title": {"romaji": "Test", "english": "Test", "native": None},
                "synonyms": [],
                "format": "TV",
                "seasonYear": 2026,
                "coverImage": {"large": None},
                "description": "Description",
                "status": "RELEASING",
                "startDate": {"year": 2026, "month": 1, "day": 2},
                "genres": ["Action", "Drama"],
                "averageScore": 83,
                "duration": 24,
            }
            data = {"Media": media} if "AnimeDetails" in document else {"Page": {"media": [media]}}
            return httpx.Response(200, json={"data": data})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            provider = AniListProvider(client)
            result = provider.search("test")[0]
            details = provider.details("1")

        self.assertEqual(result.genres, ["Action", "Drama"])
        self.assertEqual(result.average_rating, 83)
        self.assertEqual(details.episode_runtime_minutes, 24)

    def test_kitsu_reads_categories_and_series_metadata(self) -> None:
        resource = {
            "id": "1",
            "type": "anime",
            "attributes": {
                "canonicalTitle": "Test",
                "titles": {"en": "Test"},
                "startDate": "2026-01-02",
                "averageRating": "81.5",
                "episodeLength": 25,
                "status": "current",
            },
            "relationships": {"categories": {"data": [{"type": "categories", "id": "7"}]}},
        }
        payload = {
            "data": [resource],
            "included": [{"type": "categories", "id": "7", "attributes": {"title": "Drama"}}],
        }

        def handler(request: httpx.Request) -> httpx.Response:
            body = payload if request.url.path.endswith("/anime") else {**payload, "data": resource}
            return httpx.Response(200, json=body)

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            provider = KitsuProvider(client)
            result = provider.search("test")[0]
            details = provider.details("1")

        self.assertEqual(result.genres, ["Drama"])
        self.assertEqual(result.average_rating, 81.5)
        self.assertEqual(details.episode_runtime_minutes, 25)

    def test_tmdb_reads_show_rating_and_episode_runtime(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/season/1"):
                return httpx.Response(
                    200,
                    json={
                        "episodes": [
                            {
                                "id": 11,
                                "season_number": 1,
                                "episode_number": 1,
                                "name": "Pilot",
                                "air_date": "2026-01-03",
                                "runtime": 52,
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "name": "Test",
                    "overview": "Description",
                    "first_air_date": "2026-01-02",
                    "status": "Returning Series",
                    "genres": [{"id": 18, "name": "Drama"}],
                    "vote_average": 8.4,
                    "episode_run_time": [50],
                    "seasons": [{"season_number": 1}],
                },
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            provider = TmdbProvider(client, "token")
            details = provider.details("1")
            episodes = provider.episodes("1")

        self.assertEqual(details.genres, ["Drama"])
        self.assertEqual(details.average_rating, 84)
        self.assertEqual(details.episode_runtime_minutes, 50)
        self.assertEqual(episodes[0].duration_minutes, 52)


if __name__ == "__main__":
    unittest.main()

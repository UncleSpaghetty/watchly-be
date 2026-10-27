import re
from datetime import UTC, date, datetime
from typing import Any, Literal

import httpx

from app.providers.base import (
    USER_AGENT,
    EpisodeInfo,
    ProviderError,
    SearchResult,
    TitleDetails,
    request_json,
)

ENDPOINT = "https://graphql.anilist.co"
MAX_EPISODE_PAGES = 10

SEARCH_DOC = """
query SearchAnime($search: String!, $perPage: Int!) {
  Page(page: 1, perPage: $perPage) {
    media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
      id title { romaji english native } synonyms format seasonYear coverImage { large }
      genres averageScore duration
    }
  }
}
"""
DETAILS_DOC = """
query AnimeDetails($id: Int!) {
  Media(id: $id, type: ANIME) {
    description(asHtml: false) status startDate { year month day }
    genres averageScore duration
  }
}
"""
EPISODES_DOC = """
query AnimeEpisodes($id: Int!, $page: Int!) {
  Media(id: $id, type: ANIME) {
    airingSchedule(page: $page, perPage: 50) {
      pageInfo { hasNextPage }
      nodes { episode airingAt }
    }
  }
}
"""


def _html_to_text(value: str) -> str:
    return re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", value, flags=re.I)).strip()


class AniListProvider:
    source = "anilist"
    kind: Literal["anime", "tv"] = "anime"

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def _query(self, document: str, variables: dict[str, Any]) -> dict[str, Any]:
        payload = request_json(
            self._client,
            self.source,
            "POST",
            ENDPOINT,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            json={"query": document, "variables": variables},
        )
        if not isinstance(payload, dict) or payload.get("errors") or not payload.get("data"):
            raise ProviderError("anilist", "invalid-response", "AniList ha rifiutato la richiesta.")
        data: dict[str, Any] = payload["data"]
        return data

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        data = self._query(SEARCH_DOC, {"search": query, "perPage": limit})
        media = (data.get("Page") or {}).get("media")
        if not isinstance(media, list):
            raise ProviderError("anilist", "invalid-response", "Risposta AniList senza risultati.")
        results: list[SearchResult] = []
        for item in media:
            titles = item.get("title") or {}
            title = titles.get("english") or titles.get("romaji") or titles.get("native")
            if not title:
                continue
            alternatives = [
                titles.get("romaji"),
                titles.get("native"),
                *(item.get("synonyms") or []),
            ]
            results.append(
                SearchResult(
                    source=self.source,
                    external_id=str(item["id"]),
                    title=title,
                    kind="anime",
                    alternative_titles=list(
                        dict.fromkeys(a for a in alternatives if a and a != title)
                    ),
                    format=item.get("format"),
                    year=item.get("seasonYear"),
                    poster_url=(item.get("coverImage") or {}).get("large"),
                    genres=[str(value) for value in item.get("genres") or [] if value],
                    average_rating=float(item["averageScore"])
                    if item.get("averageScore") is not None
                    else None,
                    episode_runtime_minutes=item.get("duration"),
                )
            )
        return results

    def details(self, external_id: str) -> TitleDetails:
        data = self._query(DETAILS_DOC, {"id": int(external_id)})
        media = data.get("Media") or {}
        start = media.get("startDate") or {}
        start_date = None
        if start.get("year") and start.get("month") and start.get("day"):
            start_date = date(start["year"], start["month"], start["day"])
        description = media.get("description")
        return TitleDetails(
            synopsis=_html_to_text(description) if description else None,
            start_date=start_date,
            status=media.get("status"),
            genres=[str(value) for value in media.get("genres") or [] if value],
            average_rating=float(media["averageScore"])
            if media.get("averageScore") is not None
            else None,
            episode_runtime_minutes=media.get("duration"),
        )

    def episodes(self, external_id: str) -> list[EpisodeInfo]:
        episodes: list[EpisodeInfo] = []
        for page in range(1, MAX_EPISODE_PAGES + 1):
            data = self._query(EPISODES_DOC, {"id": int(external_id), "page": page})
            schedule = (data.get("Media") or {}).get("airingSchedule")
            if not schedule or not isinstance(schedule.get("nodes"), list):
                raise ProviderError(
                    "anilist", "invalid-response", "Risposta AniList senza episodi."
                )
            for node in schedule["nodes"]:
                airing = datetime.fromtimestamp(node["airingAt"], UTC)
                episodes.append(
                    EpisodeInfo(
                        external_id=str(node["episode"]),
                        season_number=None,
                        number=node["episode"],
                        title=None,
                        air_date=None,  # derivata dal timestamp nel servizio di sync
                        air_at=airing,
                    )
                )
            if not (schedule.get("pageInfo") or {}).get("hasNextPage"):
                break
        return sorted(episodes, key=lambda e: e.number or 0)

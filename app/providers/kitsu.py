from typing import Literal

import httpx

from app.providers.base import (
    USER_AGENT,
    EpisodeInfo,
    ProviderError,
    SearchResult,
    TitleDetails,
    parse_iso_date,
    request_json,
)

BASE = "https://kitsu.io/api/edge"
HEADERS = {"Accept": "application/vnd.api+json", "User-Agent": USER_AGENT}
MAX_EPISODE_PAGES = 30


def _number(value: object) -> float | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_int(value: object) -> int | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _category_names(payload: dict[str, object], item: dict[str, object]) -> list[str]:
    included = payload.get("included")
    names: dict[str, str] = {}
    if isinstance(included, list):
        for resource in included:
            if not isinstance(resource, dict) or resource.get("type") != "categories":
                continue
            attrs = resource.get("attributes")
            title = attrs.get("title") if isinstance(attrs, dict) else None
            if title:
                names[str(resource.get("id"))] = str(title)
    relationships = item.get("relationships")
    categories = relationships.get("categories") if isinstance(relationships, dict) else None
    data = categories.get("data") if isinstance(categories, dict) else None
    if not isinstance(data, list):
        return []
    return list(
        dict.fromkeys(
            names[str(row.get("id"))]
            for row in data
            if isinstance(row, dict) and str(row.get("id")) in names
        )
    )


class KitsuProvider:
    source = "kitsu"
    kind: Literal["anime", "tv"] = "anime"

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def _get(self, url: str, params: dict[str, str] | None = None) -> dict[str, object]:
        payload = request_json(
            self._client, self.source, "GET", url, headers=HEADERS, params=params
        )
        if not isinstance(payload, dict):
            raise ProviderError("kitsu", "invalid-response", "Risposta Kitsu non valida.")
        return payload

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        payload = self._get(
            f"{BASE}/anime",
            {"filter[text]": query, "page[limit]": str(limit), "include": "categories"},
        )
        data = payload.get("data")
        if not isinstance(data, list):
            raise ProviderError("kitsu", "invalid-response", "Risposta Kitsu senza risultati.")
        results: list[SearchResult] = []
        for item in data:
            attrs = item.get("attributes") or {}
            titles = attrs.get("titles") or {}
            title = titles.get("it_it") or titles.get("en") or attrs.get("canonicalTitle")
            title = title or titles.get("en_jp")
            if not title:
                continue
            alternatives = [
                attrs.get("canonicalTitle"),
                titles.get("en"),
                titles.get("en_jp"),
                *(attrs.get("abbreviatedTitles") or []),
            ]
            start = parse_iso_date(attrs.get("startDate"))
            results.append(
                SearchResult(
                    source=self.source,
                    external_id=str(item["id"]),
                    title=title,
                    kind="anime",
                    alternative_titles=list(
                        dict.fromkeys(a for a in alternatives if a and a != title)
                    ),
                    format=attrs.get("subtype"),
                    year=start.year if start else None,
                    poster_url=(attrs.get("posterImage") or {}).get("small"),
                    synopsis=attrs.get("synopsis") or None,
                    genres=_category_names(payload, item),
                    average_rating=_number(attrs.get("averageRating")),
                    episode_runtime_minutes=_positive_int(attrs.get("episodeLength")),
                )
            )
        return results

    def details(self, external_id: str) -> TitleDetails:
        payload = self._get(f"{BASE}/anime/{external_id}", {"include": "categories"})
        data = payload.get("data")
        attrs = (data.get("attributes") if isinstance(data, dict) else None) or {}
        return TitleDetails(
            synopsis=attrs.get("synopsis") or None,
            start_date=parse_iso_date(attrs.get("startDate")),
            status=attrs.get("status"),
            genres=_category_names(payload, data) if isinstance(data, dict) else [],
            average_rating=_number(attrs.get("averageRating")),
            episode_runtime_minutes=_positive_int(attrs.get("episodeLength")),
        )

    def episodes(self, external_id: str) -> list[EpisodeInfo]:
        url: str | None = f"{BASE}/anime/{external_id}/episodes"
        params: dict[str, str] | None = {"page[limit]": "20", "sort": "number"}
        episodes: list[EpisodeInfo] = []
        for _ in range(MAX_EPISODE_PAGES):
            if not url:
                break
            payload = self._get(url, params)
            data = payload.get("data")
            if not isinstance(data, list):
                raise ProviderError("kitsu", "invalid-response", "Risposta Kitsu senza episodi.")
            for item in data:
                attrs = item.get("attributes") or {}
                episodes.append(
                    EpisodeInfo(
                        external_id=str(item["id"]),
                        season_number=attrs.get("seasonNumber"),
                        number=attrs.get("number"),
                        title=attrs.get("canonicalTitle"),
                        air_date=parse_iso_date(attrs.get("airdate")),
                        duration_minutes=_positive_int(attrs.get("length")),
                    )
                )
            links = payload.get("links")
            url = links.get("next") if isinstance(links, dict) else None
            params = None  # il link next contiene già i parametri
        return episodes

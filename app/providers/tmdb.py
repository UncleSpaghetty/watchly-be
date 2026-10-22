from typing import Literal

import httpx

from app.providers.base import (
    EpisodeInfo,
    ProviderError,
    SearchResult,
    TitleDetails,
    parse_iso_date,
    request_json,
)

BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w185"


class TmdbProvider:
    source = "tmdb"
    kind: Literal["anime", "tv"] = "tv"

    def __init__(self, client: httpx.Client, read_token: str | None) -> None:
        self._client = client
        self._token = read_token

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, object]:
        if not self._token:
            raise ProviderError("tmdb", "not-configured", "TMDB non è configurato.")
        payload = request_json(
            self._client,
            self.source,
            "GET",
            f"{BASE}{path}",
            headers={"Accept": "application/json", "Authorization": f"Bearer {self._token}"},
            params={"language": "it-IT", **(params or {})},
        )
        if not isinstance(payload, dict):
            raise ProviderError("tmdb", "invalid-response", "Risposta TMDB non valida.")
        return payload

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        payload = self._get("/search/tv", {"query": query, "include_adult": "false"})
        results = payload.get("results")
        if not isinstance(results, list):
            raise ProviderError("tmdb", "invalid-response", "Risposta TMDB senza risultati.")
        out: list[SearchResult] = []
        for item in results[:limit]:
            title = item.get("name") or item.get("original_name")
            if not title:
                continue
            first = parse_iso_date(item.get("first_air_date"))
            original = item.get("original_name")
            out.append(
                SearchResult(
                    source=self.source,
                    external_id=str(item["id"]),
                    title=title,
                    kind="tv",
                    alternative_titles=[original] if original and original != title else [],
                    format="TV",
                    year=first.year if first else None,
                    poster_url=f"{IMAGE_BASE}{item['poster_path']}"
                    if item.get("poster_path")
                    else None,
                    synopsis=item.get("overview") or None,
                )
            )
        return out

    def details(self, external_id: str) -> TitleDetails:
        payload = self._get(f"/tv/{external_id}")
        return TitleDetails(
            synopsis=str(payload.get("overview") or "") or None,
            start_date=parse_iso_date(str(payload.get("first_air_date") or "")),
            status=str(payload["status"]) if payload.get("status") else None,
        )

    def episodes(self, external_id: str) -> list[EpisodeInfo]:
        show = self._get(f"/tv/{external_id}")
        seasons = show.get("seasons")
        if not isinstance(seasons, list):
            raise ProviderError("tmdb", "invalid-response", "Risposta TMDB senza stagioni.")
        episodes: list[EpisodeInfo] = []
        for season in seasons:
            number = season.get("season_number")
            if not number:  # stagione 0 = speciali
                continue
            payload = self._get(f"/tv/{external_id}/season/{number}")
            for item in payload.get("episodes") or []:  # type: ignore[attr-defined]
                episodes.append(
                    EpisodeInfo(
                        external_id=str(item["id"]),
                        season_number=item.get("season_number", number),
                        number=item.get("episode_number"),
                        title=item.get("name") or None,
                        air_date=parse_iso_date(item.get("air_date")),
                    )
                )
        return episodes

from typing import Literal, cast

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
LOGO_BASE = "https://image.tmdb.org/t/p/w92"


def _positive_int(value: object) -> int | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _rating(value: object) -> float | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value) * 10
    except ValueError:
        return None


class TmdbProvider:
    source = "tmdb"
    kind: Literal["anime", "tv"] = "tv"

    def __init__(self, client: httpx.Client, read_token: str | None) -> None:
        self._client = client
        self._token = read_token
        self._show_cache: dict[str, dict[str, object]] = {}

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

    def _show(self, external_id: str) -> dict[str, object]:
        if external_id not in self._show_cache:
            self._show_cache[external_id] = self._get(f"/tv/{external_id}")
        return self._show_cache[external_id]

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
                    average_rating=_rating(item.get("vote_average")),
                )
            )
        return out

    def details(self, external_id: str) -> TitleDetails:
        payload = self._show(external_id)
        provider_payload = self._get(f"/tv/{external_id}/watch/providers")
        results = provider_payload.get("results")
        italy = (
            cast(dict[str, object], results.get("IT") or {}) if isinstance(results, dict) else {}
        )
        watch_providers: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for access_type in ("flatrate", "free", "ads", "buy", "rent"):
            raw_items = italy.get(access_type)
            for item in raw_items if isinstance(raw_items, list) else []:
                if not isinstance(item, dict):
                    continue
                provider_id = str(item.get("provider_id") or item.get("provider_name") or "")
                key = (provider_id, access_type)
                if not provider_id or key in seen:
                    continue
                seen.add(key)
                watch_providers.append(
                    {
                        "id": f"tmdb:{provider_id}",
                        "name": str(item.get("provider_name") or "Servizio streaming"),
                        "url": str(
                            italy.get("link")
                            or f"https://www.themoviedb.org/tv/{external_id}/watch"
                        ),
                        "type": access_type,
                        "source": "tmdb",
                        **(
                            {"logo_url": f"{LOGO_BASE}{item['logo_path']}"}
                            if item.get("logo_path")
                            else {}
                        ),
                    }
                )
        genres = payload.get("genres")
        raw_runtimes = payload.get("episode_run_time")
        runtimes = [
            value
            for value in (
                _positive_int(item)
                for item in (raw_runtimes if isinstance(raw_runtimes, list) else [])
            )
            if value is not None
        ]
        return TitleDetails(
            synopsis=str(payload.get("overview") or "") or None,
            start_date=parse_iso_date(str(payload.get("first_air_date") or "")),
            status={
                "Returning Series": "releasing",
                "In Production": "releasing",
                "Planned": "upcoming",
                "Pilot": "upcoming",
                "Ended": "finished",
                "Canceled": "cancelled",
            }.get(str(payload.get("status"))),
            genres=[
                str(item["name"]) for item in genres if isinstance(item, dict) and item.get("name")
            ]
            if isinstance(genres, list)
            else [],
            average_rating=_rating(payload.get("vote_average")),
            episode_runtime_minutes=round(sum(runtimes) / len(runtimes)) if runtimes else None,
            watch_providers=watch_providers,
        )

    def episodes(self, external_id: str) -> list[EpisodeInfo]:
        show = self._show(external_id)
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
                        duration_minutes=_positive_int(item.get("runtime")),
                    )
                )
        return episodes

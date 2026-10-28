import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal, Protocol

import httpx

logger = logging.getLogger(__name__)

SourceName = Literal["kitsu", "anilist", "tmdb"]
SOURCE_LABELS: dict[str, str] = {"kitsu": "Kitsu", "anilist": "AniList", "tmdb": "TMDB"}
USER_AGENT = "watchly-be/0.1 (+https://github.com/UncleSpaghetty/watchly-be)"


class ProviderError(Exception):
    def __init__(self, source: str, kind: str, message: str) -> None:
        super().__init__(message)
        self.source = source
        self.kind = kind  # unavailable | rate-limited | network | invalid-response | not-configured
        self.message = message


@dataclass
class SearchResult:
    source: str
    external_id: str
    title: str
    kind: Literal["anime", "tv"]
    alternative_titles: list[str] = field(default_factory=list)
    format: str | None = None
    year: int | None = None
    poster_url: str | None = None
    synopsis: str | None = None
    genres: list[str] = field(default_factory=list)
    average_rating: float | None = None
    episode_runtime_minutes: int | None = None
    status: str | None = None


@dataclass
class EpisodeInfo:
    external_id: str
    season_number: int | None
    number: int | None
    title: str | None
    air_date: date | None
    air_at: datetime | None = None
    duration_minutes: int | None = None


@dataclass
class TitleDetails:
    synopsis: str | None = None
    start_date: date | None = None
    status: str | None = None
    genres: list[str] = field(default_factory=list)
    average_rating: float | None = None
    episode_runtime_minutes: int | None = None
    watch_providers: list[dict[str, str]] = field(default_factory=list)


class CatalogProvider(Protocol):
    """Interfaccia di raccolta e normalizzazione: la logica di business non vede schemi esterni."""

    source: str
    kind: Literal["anime", "tv"]

    def search(self, query: str, limit: int = 20) -> list[SearchResult]: ...

    def details(self, external_id: str) -> TitleDetails: ...

    def episodes(self, external_id: str) -> list[EpisodeInfo]: ...


def request_json(
    client: httpx.Client,
    source: str,
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    json: Any = None,
    params: Mapping[str, str] | None = None,
    retries: int = 3,
) -> Any:
    """Richiesta con retry/backoff su 429 e 5xx, rispettando Retry-After."""
    label = SOURCE_LABELS.get(source, source)
    for attempt in range(retries):
        last = attempt == retries - 1
        try:
            response = client.request(
                method, url, headers=headers, json=json, params=params, timeout=15.0
            )
        except httpx.HTTPError as exc:
            if last:
                raise ProviderError(source, "network", f"Impossibile contattare {label}.") from exc
            time.sleep(2**attempt)
            continue

        if response.status_code == 429 or response.status_code >= 500:
            if last:
                kind = "rate-limited" if response.status_code == 429 else "unavailable"
                raise ProviderError(source, kind, f"{label} non è al momento disponibile.")
            retry_after = response.headers.get("Retry-After", "")
            delay = min(float(retry_after), 30.0) if retry_after.isdigit() else float(2**attempt)
            time.sleep(delay)
            continue

        if response.status_code >= 400:
            raise ProviderError(source, "invalid-response", f"{label} ha rifiutato la richiesta.")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(
                source, "invalid-response", f"Risposta di {label} non valida."
            ) from exc
    raise ProviderError(source, "unavailable", f"{label} non è al momento disponibile.")


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None

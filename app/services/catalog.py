import logging
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.series import Series
from app.models.series_external_id import SeriesExternalId
from app.providers.anilist import AniListProvider
from app.providers.base import CatalogProvider, ProviderError, SearchResult
from app.providers.kitsu import KitsuProvider
from app.providers.tmdb import TmdbProvider
from app.services.matching import find_match

logger = logging.getLogger(__name__)


@contextmanager
def provider_registry() -> Iterator[dict[str, CatalogProvider]]:
    settings = get_settings()
    with httpx.Client() as client:
        yield {
            "kitsu": KitsuProvider(client),
            "anilist": AniListProvider(client),
            "tmdb": TmdbProvider(client, settings.tmdb_read_token),
        }


@dataclass
class SearchOutcome:
    series: list[Series] = field(default_factory=list)
    provider_errors: dict[str, str] = field(default_factory=dict)


def upsert_result(db: Session, result: SearchResult) -> Series:
    existing = db.scalar(
        select(Series)
        .join(SeriesExternalId)
        .where(
            SeriesExternalId.source == result.source,
            SeriesExternalId.external_id == result.external_id,
        )
    )
    series = existing or find_match(db, result)
    if series is None:
        # I default delle colonne SQLAlchemy vengono applicati al flush: inizializziamo
        # qui le collezioni che vengono lette e aggiornate prima della INSERT.
        series = Series(
            kind=result.kind,
            title=result.title,
            alternative_titles=[],
            genres=[],
        )
        db.add(series)
    if not any(e.source == result.source for e in series.external_ids):
        series.external_ids.append(
            SeriesExternalId(source=result.source, external_id=result.external_id)
        )

    aliases = dict.fromkeys([*series.alternative_titles, result.title, *result.alternative_titles])
    series.alternative_titles = [a for a in aliases if a and a != series.title]
    series.poster_url = series.poster_url or result.poster_url
    series.synopsis = series.synopsis or result.synopsis
    series.format = series.format or result.format
    series.status = series.status or result.status
    if result.genres:
        series.genres = list(dict.fromkeys([*(series.genres or []), *result.genres]))
    if result.average_rating is not None:
        series.average_rating = result.average_rating
        series.rating_source = result.source
    series.episode_runtime_minutes = (
        result.episode_runtime_minutes or series.episode_runtime_minutes
    )
    series.year = series.year or result.year
    db.flush()
    return series


def search_catalog(
    db: Session,
    query: str,
    kind: str | None = None,
    source: str | None = None,
    *,
    year: int | None = None,
    format: str | None = None,
    genre: str | None = None,
    status: str | None = None,
    sort: str = "relevance",
) -> SearchOutcome:
    outcome = SearchOutcome()
    with provider_registry() as providers:
        selected = {
            name: p
            for name, p in providers.items()
            if (kind in (None, "all") or p.kind == kind) and (source in (None, name))
        }

        def run(item: tuple[str, CatalogProvider]) -> tuple[str, list[SearchResult] | str]:
            name, provider = item
            try:
                return name, provider.search(query)
            except ProviderError as exc:
                return name, exc.message
            except Exception:
                logger.exception("search failed for %s", name)
                return name, "Errore imprevisto del provider."

        with ThreadPoolExecutor(max_workers=max(1, len(selected))) as pool:
            responses = list(pool.map(run, selected.items()))

    seen: set[str] = set()
    for name, payload in responses:
        if isinstance(payload, str):
            outcome.provider_errors[name] = payload
            continue
        for result in payload:
            series = upsert_result(db, result)
            if str(series.id) not in seen:
                seen.add(str(series.id))
                outcome.series.append(series)
    if year is not None:
        outcome.series = [series for series in outcome.series if series.year == year]
    if format:
        normalized = format.casefold()
        outcome.series = [
            series for series in outcome.series if (series.format or "").casefold() == normalized
        ]
    if genre:
        normalized = genre.casefold()
        outcome.series = [
            series
            for series in outcome.series
            if any(value.casefold() == normalized for value in (series.genres or []))
        ]
    if status:
        normalized = status.casefold()
        outcome.series = [
            series for series in outcome.series if (series.status or "").casefold() == normalized
        ]
    if sort == "rating":
        outcome.series.sort(key=lambda series: series.average_rating or -1, reverse=True)
    elif sort == "year":
        outcome.series.sort(key=lambda series: series.year or -1, reverse=True)
    elif sort == "title":
        outcome.series.sort(key=lambda series: series.title.casefold())
    db.commit()
    return outcome

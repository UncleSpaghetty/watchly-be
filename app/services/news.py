import hashlib
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data_source import DataSource
from app.models.news_article import NewsArticle
from app.models.news_series_link import NewsSeriesLink
from app.models.provider_cache import ProviderCache
from app.models.series import Series
from app.providers.rss import FeedItem, RssProvider
from app.services.matching import normalize_title

logger = logging.getLogger(__name__)

MIN_ALIAS_LENGTH = 4


def classify_article(title: str) -> str:
    normalized = normalize_title(title)
    rules = {
        "manga": ("manga", "manhwa", "fumetto", "comic"),
        "gaming": ("game", "gaming", "videogioco", "playstation", "xbox", "nintendo"),
        "events": ("evento", "festival", "convention", "comic con"),
        "anime": ("anime", "animazione", "crunchyroll"),
    }
    for category, keywords in rules.items():
        if any(keyword in normalized for keyword in keywords):
            return category
    return "series"


def feed_source_id(url: str) -> str:
    return "rss-" + hashlib.sha1(url.encode()).hexdigest()[:12]  # noqa: S324 - solo identificativo


def _alias_index(db: Session) -> list[tuple[Series, str, float]]:
    index: list[tuple[Series, str, float]] = []
    for series in db.scalars(select(Series)).all():
        primary = {normalize_title(t) for t in (series.title, series.original_title) if t}
        aliases = {normalize_title(t) for t in series.alternative_titles if t}
        for alias in primary | aliases:
            if len(alias) >= MIN_ALIAS_LENGTH:
                index.append((series, alias, 0.9 if alias in primary else 0.75))
    return index


def match_article(title: str, index: list[tuple[Series, str, float]]) -> list[tuple[Series, float]]:
    """Collega una news a una serie solo se il titolo più specifico (alias più lungo) trovato
    nell'articolo identifica una sola serie; in caso di ambiguità non collega nulla."""
    padded = f" {normalize_title(title)} "
    hits = [(s, a, c) for s, a, c in index if f" {a} " in padded]
    if not hits:
        return []
    longest = max(len(a) for _, a, _ in hits)
    top = {s.id: (s, c) for s, a, c in hits if len(a) == longest}
    return list(top.values()) if len(top) == 1 else []


def _ensure_source(db: Session, url: str) -> DataSource:
    source_id = feed_source_id(url)
    source = db.get(DataSource, source_id)
    if source is None:
        host = httpx.URL(url).host
        source = DataSource(id=source_id, name=host, terms_url=url)
        db.add(source)
        db.flush()
    return source


def _store(
    db: Session, source: DataSource, item: FeedItem, index: list[tuple[Series, str, float]]
) -> None:
    article = db.scalar(select(NewsArticle).where(NewsArticle.external_url == item.url))
    if article is None:
        article = NewsArticle(source_id=source.id, external_url=item.url, title=item.title)
        db.add(article)
    article.title = item.title[:500]
    article.published_at = item.published_at
    article.excerpt = item.excerpt
    article.image_url = item.image_url
    article.category = classify_article(item.title)
    article.last_seen_at = datetime.now(UTC)
    db.flush()
    for series, confidence in match_article(item.title, index):
        link = db.get(NewsSeriesLink, (article.id, series.id))
        if link is None:
            db.add(
                NewsSeriesLink(
                    news_id=article.id,
                    series_id=series.id,
                    match_method="alias",
                    confidence=confidence,
                )
            )


def refresh_news(db: Session, feed_urls: list[str]) -> dict[str, str]:
    """Aggiorna i feed con fetch condizionale; restituisce gli errori per feed."""
    errors: dict[str, str] = {}
    if not feed_urls:
        return errors
    index = _alias_index(db)
    with httpx.Client() as client:
        rss = RssProvider(client)
        for url in feed_urls:
            source = _ensure_source(db, url)
            cache = db.get(ProviderCache, url)
            try:
                result = rss.fetch(
                    url,
                    cache.etag if cache else None,
                    cache.last_modified if cache else None,
                )
                for item in result.items:
                    _store(db, source, item, index)
                if cache is None:
                    cache = ProviderCache(key=url, fetched_at=datetime.now(UTC))
                    db.add(cache)
                cache.etag, cache.last_modified = result.etag, result.last_modified
                cache.fetched_at = datetime.now(UTC)
                cache.last_status = "not_modified" if result.not_modified else "ok"
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.warning("news feed failed: %s (%s)", url, type(exc).__name__)
                errors[url] = type(exc).__name__
    return errors

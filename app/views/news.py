import base64
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import and_, func, or_, select

from app.errors import ApiError
from app.models.following import Following
from app.models.news_article import NewsArticle
from app.models.news_series_link import NewsSeriesLink
from app.models.series import Series
from app.schemas.news import NewsPage, NewsRead
from app.schemas.series import SeriesSummary
from app.settings.security import CurrentUser, Db

router = APIRouter(prefix="/news", tags=["news"])
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _encode(published: datetime | None, article_id: UUID) -> str:
    stamp = (published or EPOCH).isoformat()
    return base64.urlsafe_b64encode(f"{stamp}|{article_id}".encode()).decode()


def _decode(cursor: str) -> tuple[datetime, UUID]:
    try:
        stamp, raw_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(stamp), UUID(raw_id)
    except Exception as exc:
        raise ApiError(400, "invalid_cursor", "Cursor non valido") from exc


@router.get("", response_model=NewsPage)
def list_news(
    user: CurrentUser,
    db: Db,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    kind: Literal["anime", "tv"] | None = None,
    series_id: UUID | None = None,
    followed: bool = False,
) -> NewsPage:
    # Ordinamento stabile: data (le news senza data in coda tramite EPOCH) e id.
    order_date = func.coalesce(NewsArticle.published_at, EPOCH)
    stmt = select(NewsArticle).order_by(order_date.desc(), NewsArticle.id.desc())
    if series_id or kind or followed:
        link_filter = [NewsSeriesLink.news_id == NewsArticle.id]
        if series_id:
            link_filter.append(NewsSeriesLink.series_id == series_id)
        if kind:
            link_filter.append(
                NewsSeriesLink.series_id.in_(select(Series.id).where(Series.kind == kind))
            )
        if followed:
            link_filter.append(
                NewsSeriesLink.series_id.in_(
                    select(Following.series_id).where(Following.user_id == user.id)
                )
            )
        stmt = stmt.where(select(NewsSeriesLink.news_id).where(*link_filter).exists())
    if cursor:
        c_date, c_id = _decode(cursor)
        stmt = stmt.where(
            or_(
                order_date < c_date,
                and_(order_date == c_date, NewsArticle.id < c_id),
            )
        )
    articles = list(db.scalars(stmt.limit(limit + 1)).all())
    page, more = articles[:limit], len(articles) > limit

    ids = [a.id for a in page]
    links = db.execute(
        select(NewsSeriesLink, Series)
        .join(Series, Series.id == NewsSeriesLink.series_id)
        .where(NewsSeriesLink.news_id.in_(ids))
    ).all()
    by_article: dict[UUID, list[tuple[NewsSeriesLink, Series]]] = {}
    for link, series in links:
        by_article.setdefault(link.news_id, []).append((link, series))

    items = [
        NewsRead(
            id=a.id,
            source=a.source_id,
            url=a.external_url,
            title=a.title,
            published_at=a.published_at,
            excerpt=a.excerpt,
            image_url=a.image_url,
            series=[SeriesSummary.model_validate(s) for _, s in by_article.get(a.id, [])],
            confidence=max((link.confidence for link, _ in by_article.get(a.id, [])), default=None),
        )
        for a in page
    ]
    next_cursor = _encode(page[-1].published_at, page[-1].id) if more and page else None
    return NewsPage(items=items, next_cursor=next_cursor)

# Built-in
import base64
from datetime import UTC, datetime
from uuid import UUID

# Flask
from flask import request

# Third-party
from sqlalchemy import and_, func, or_, select

# Config
from app.config import get_settings
from app.errors import ApiError

# Models
from app.models.data_source import DataSource
from app.models.following import Following
from app.models.news_article import NewsArticle
from app.models.news_series_link import NewsSeriesLink
from app.models.series import Series

# Schemas
from app.schemas.news.news_read import NewsReadSchema

# Views
from app.views.base import WatchlyView

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _encode(published: datetime | None, article_id: UUID) -> str:
    return base64.urlsafe_b64encode(
        f"{(published or EPOCH).isoformat()}|{article_id}".encode()
    ).decode()


def _decode(cursor: str) -> tuple[datetime, UUID]:
    try:
        stamp, raw_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(stamp), UUID(raw_id)
    except Exception as exc:
        raise ApiError(400, "invalid_cursor", "Cursor non valido") from exc


class NewsView(WatchlyView):
    accepted_methods = ["GET"]

    def get(self):
        cursor = request.args.get("cursor")
        kind = request.args.get("kind")
        followed = request.args.get("followed", "false").lower() in {"true", "1", "yes"}
        try:
            limit = int(request.args.get("limit", "20"))
            series_id = UUID(request.args["series_id"]) if request.args.get("series_id") else None
        except (ValueError, TypeError) as exc:
            raise ApiError(422, "validation_error", "Filtro news non valido") from exc
        if not 1 <= limit <= 50 or kind not in {None, "anime", "tv"}:
            raise ApiError(422, "validation_error", "Filtro news non valido")

        order_date = func.coalesce(NewsArticle.published_at, EPOCH)
        statement = select(NewsArticle).order_by(order_date.desc(), NewsArticle.id.desc())
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
                        select(Following.series_id).where(Following.user_id == self.user.id)
                    )
                )
            statement = statement.where(select(NewsSeriesLink.news_id).where(*link_filter).exists())
        if cursor:
            cursor_date, cursor_id = _decode(cursor)
            statement = statement.where(
                or_(
                    order_date < cursor_date,
                    and_(order_date == cursor_date, NewsArticle.id < cursor_id),
                )
            )
        articles = list(self.session.scalars(statement.limit(limit + 1)).all())
        page, more = articles[:limit], len(articles) > limit
        links = self.session.execute(
            select(NewsSeriesLink, Series)
            .join(Series, Series.id == NewsSeriesLink.series_id)
            .where(NewsSeriesLink.news_id.in_([article.id for article in page]))
        ).all()
        by_article: dict[UUID, list[tuple[NewsSeriesLink, Series]]] = {}
        for link, series in links:
            by_article.setdefault(link.news_id, []).append((link, series))
        followed_ids = set(
            self.session.scalars(
                select(Following.series_id).where(Following.user_id == self.user.id)
            ).all()
        )
        source_ids = {article.source_id for article in page}
        source_names = {
            source.id: source.name
            for source in self.session.scalars(
                select(DataSource).where(DataSource.id.in_(source_ids))
            ).all()
        }
        items = [
            NewsReadSchema().dump(
                {
                    "id": article.id,
                    "source": source_names.get(article.source_id, article.source_id),
                    "url": article.external_url,
                    "title": article.title,
                    "published_at": article.published_at,
                    "excerpt": article.excerpt,
                    "image_url": article.image_url,
                    "series": [
                        {
                            "id": series.id,
                            "title": series.title,
                            "followed": series.id in followed_ids,
                        }
                        for _, series in by_article.get(article.id, [])
                    ],
                    "confidence": max(
                        (link.confidence for link, _ in by_article.get(article.id, [])),
                        default=None,
                    ),
                }
            )
            for article in page
        ]
        next_cursor = _encode(page[-1].published_at, page[-1].id) if more and page else None
        return {
            "items": items,
            "next_cursor": next_cursor,
            "configured": bool(get_settings().news_feed_urls),
        }

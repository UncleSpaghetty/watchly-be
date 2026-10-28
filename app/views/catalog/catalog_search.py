# Flask
from flask import request

# Third-party
from sqlalchemy import select

from app.errors import ApiError

# Models
from app.models.following import Following

# Services
from app.services.catalog import search_catalog
from app.services.series import dump_series

# Config
from app.settings.security import RateLimiter

# Views
from app.views.base import WatchlyView

search_limit = RateLimiter(limit=30, window_seconds=60, scope="catalog-search")


class CatalogSearchView(WatchlyView):
    accepted_methods = ["GET"]
    rate_limiter = search_limit

    def get(self):
        query = request.args.get("q", "").strip()
        kind = request.args.get("kind", "all")
        source = request.args.get("source")
        raw_year = request.args.get("year")
        format_filter = request.args.get("format")
        genre = request.args.get("genre")
        status = request.args.get("status")
        sort = request.args.get("sort", "relevance")
        try:
            year = int(raw_year) if raw_year else None
        except ValueError as exc:
            raise ApiError(422, "validation_error", "Anno non valido") from exc
        if not 2 <= len(query) <= 100:
            raise ApiError(422, "validation_error", "q deve contenere da 2 a 100 caratteri")
        if (
            kind not in {"anime", "tv", "all"}
            or source not in {None, "kitsu", "anilist", "tmdb"}
            or (year is not None and not 1900 <= year <= 2100)
            or (format_filter is not None and len(format_filter) > 50)
            or (genre is not None and len(genre) > 80)
            or (status is not None and len(status) > 50)
            or sort not in {"relevance", "rating", "year", "title"}
        ):
            raise ApiError(422, "validation_error", "Filtro catalogo non valido")
        outcome = search_catalog(
            self.session,
            query,
            kind,
            source,
            year=year,
            format=format_filter,
            genre=genre,
            status=status,
            sort=sort,
        )
        followed = set(
            self.session.scalars(
                select(Following.series_id).where(Following.user_id == self.user.id)
            ).all()
        )
        return {
            "results": [dump_series(series, series.id in followed) for series in outcome.series],
            "provider_errors": outcome.provider_errors,
        }

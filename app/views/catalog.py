from flask import request
from sqlalchemy import select

from app.errors import ApiError
from app.models.following import Following
from app.schemas.series import dump_series
from app.services.catalog import search_catalog
from app.settings.security import RateLimiter
from app.views.base import WatchlyView

search_limit = RateLimiter(limit=30, window_seconds=60, scope="catalog-search")


class CatalogSearchView(WatchlyView):
    accepted_methods = ["GET"]
    rate_limiter = search_limit

    def get(self):
        query = request.args.get("q", "").strip()
        kind = request.args.get("kind", "all")
        source = request.args.get("source")
        if not 2 <= len(query) <= 100:
            raise ApiError(422, "validation_error", "q deve contenere da 2 a 100 caratteri")
        if kind not in {"anime", "tv", "all"} or source not in {None, "kitsu", "anilist", "tmdb"}:
            raise ApiError(422, "validation_error", "Filtro catalogo non valido")
        outcome = search_catalog(self.session, query, kind, source)
        followed = set(
            self.session.scalars(
                select(Following.series_id).where(Following.user_id == self.user.id)
            ).all()
        )
        return {
            "results": [dump_series(series, series.id in followed) for series in outcome.series],
            "provider_errors": outcome.provider_errors,
        }

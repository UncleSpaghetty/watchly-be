from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.schemas.catalog import CatalogSearchResponse
from app.schemas.series import SeriesRead
from app.services.catalog import search_catalog
from app.settings.security import CurrentUser, Db, RateLimiter

router = APIRouter(prefix="/catalog", tags=["catalog"])
search_limit = RateLimiter(limit=30, window_seconds=60, scope="catalog-search")


@router.get("/search", response_model=CatalogSearchResponse, dependencies=[Depends(search_limit)])
def search(
    user: CurrentUser,
    db: Db,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    kind: Literal["anime", "tv", "all"] = "all",
    source: Literal["kitsu", "anilist", "tmdb"] | None = None,
) -> CatalogSearchResponse:
    from sqlalchemy import select

    from app.models.following import Following

    outcome = search_catalog(db, q.strip(), kind, source)
    followed = set(
        db.scalars(select(Following.series_id).where(Following.user_id == user.id)).all()
    )
    return CatalogSearchResponse(
        results=[SeriesRead.from_model(s, s.id in followed) for s in outcome.series],
        provider_errors=outcome.provider_errors,
    )

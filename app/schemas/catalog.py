from pydantic import BaseModel

from app.schemas.series import SeriesRead


class CatalogSearchResponse(BaseModel):
    results: list[SeriesRead]
    provider_errors: dict[str, str]

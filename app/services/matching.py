import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.series import Series
from app.providers.base import SearchResult


def normalize_title(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", stripped)).strip()


def series_titles(series: Series) -> set[str]:
    titles = [series.title, series.original_title, *series.alternative_titles]
    return {normalize_title(t) for t in titles if t}


def find_match(db: Session, result: SearchResult) -> Series | None:
    """Unisce due risultati solo con evidenza forte: stesso tipo, stesso anno noto, titolo
    normalizzato coincidente, un solo candidato e nessun ID già presente per quella fonte.
    Nelle ambiguità non unisce: i duplicati si risolvono esplicitamente, mai a caso."""
    if result.year is None:
        return None
    wanted = {normalize_title(t) for t in [result.title, *result.alternative_titles] if t}
    wanted.discard("")
    candidates = db.scalars(
        select(Series).where(Series.kind == result.kind, Series.year == result.year)
    ).all()
    matches = [
        s
        for s in candidates
        if series_titles(s) & wanted and all(e.source != result.source for e in s.external_ids)
    ]
    return matches[0] if len(matches) == 1 else None

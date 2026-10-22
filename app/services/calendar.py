import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.data_source import DataSource
from app.models.episode import Episode
from app.models.episode_availability import EpisodeAvailability
from app.models.following import Following
from app.models.series import Series
from app.models.watched_episode import WatchedEpisode
from app.services.availability import STATUS_RANK, is_effective

MAX_RANGE_DAYS = 100


@dataclass
class Availability:
    status: str  # confirmed | estimated | disputed | withdrawn | unknown
    service_id: str | None = None
    local_date: date | None = None
    source_id: str | None = None
    source_url: str | None = None
    evidence_type: str | None = None


@dataclass
class CalendarEntry:
    episode: Episode
    series: Series
    watched: bool
    local_date: date
    date_kind: str  # italy | original
    availability: Availability


def summarize_availability(
    rows: list[EpisodeAvailability], sources: dict[str, DataSource]
) -> Availability:
    effective = [r for r in rows if is_effective(r, sources.get(r.source_id))]
    # Una conferma non più valida degrada a "unknown": non si mostra mai come certa.
    if not effective:
        return Availability(status="unknown")
    best = min(effective, key=lambda r: (STATUS_RANK[r.status], r.available_local_date or date.max))
    return Availability(
        status=best.status,
        service_id=best.service_id,
        local_date=best.available_local_date,
        source_id=best.source_id,
        source_url=best.source_url,
        evidence_type=best.evidence_type,
    )


def load_availability(db: Session, episode_ids: list[uuid.UUID]) -> dict[uuid.UUID, Availability]:
    if not episode_ids:
        return {}
    rows = db.scalars(
        select(EpisodeAvailability).where(EpisodeAvailability.episode_id.in_(episode_ids))
    ).all()
    sources = {s.id: s for s in db.scalars(select(DataSource)).all()}
    grouped: dict[uuid.UUID, list[EpisodeAvailability]] = {}
    for row in rows:
        grouped.setdefault(row.episode_id, []).append(row)
    return {eid: summarize_availability(grouped.get(eid, []), sources) for eid in episode_ids}


def build_calendar(
    db: Session,
    user_id: uuid.UUID,
    start: date,
    end: date,
    *,
    mode: str = "all",
    kind: str | None = None,
    watched: bool | None = None,
) -> list[CalendarEntry]:
    """Episodi delle serie seguite dall'utente nell'intervallo [start, end].

    La data mostrata è quella italiana solo se confermata da evidenza valida; altrimenti
    è l'uscita originale (`date_kind="original"`) e, con mode="italy", l'episodio è escluso."""
    followed = select(Following.series_id).where(Following.user_id == user_id)
    confirmed_in_range = select(EpisodeAvailability.episode_id).where(
        EpisodeAvailability.status == "confirmed",
        EpisodeAvailability.available_local_date.between(start, end),
    )
    stmt = (
        select(Episode, Series)
        .join(Series, Series.id == Episode.series_id)
        .where(
            Episode.series_id.in_(followed),
            or_(
                Episode.original_air_date.between(start, end),
                Episode.id.in_(confirmed_in_range),
            ),
        )
    )
    if kind:
        stmt = stmt.where(Series.kind == kind)
    pairs = db.execute(stmt).all()

    availability = load_availability(db, [ep.id for ep, _ in pairs])
    watched_ids = set(
        db.scalars(
            select(WatchedEpisode.episode_id).where(
                WatchedEpisode.user_id == user_id,
                WatchedEpisode.episode_id.in_([ep.id for ep, _ in pairs]),
            )
        ).all()
    )

    entries: list[CalendarEntry] = []
    for episode, series in pairs:
        avail = availability[episode.id]
        if avail.status == "confirmed" and avail.local_date is not None:
            shown, date_kind = avail.local_date, "italy"
        elif mode != "italy" and episode.original_air_date is not None:
            shown, date_kind = episode.original_air_date, "original"
        else:
            continue
        if not start <= shown <= end:
            continue
        is_watched = episode.id in watched_ids
        if watched is not None and is_watched != watched:
            continue
        entries.append(CalendarEntry(episode, series, is_watched, shown, date_kind, avail))
    entries.sort(
        key=lambda e: (
            e.local_date,
            e.series.title.casefold(),
            e.episode.season_number or 0,
            e.episode.episode_number or 0,
        )
    )
    return entries

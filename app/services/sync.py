import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.episode import Episode
from app.models.episode_date_change import EpisodeDateChange
from app.models.following import Following
from app.models.series import Series
from app.models.sync_run import SyncRun
from app.models.user import User
from app.providers.base import CatalogProvider, EpisodeInfo, ProviderError
from app.services.catalog import provider_registry
from app.services.timeutil import to_local_date

logger = logging.getLogger(__name__)

# Una sola fonte di episodi per serie, in ordine di preferenza.
EPISODE_SOURCES = {"anime": ["kitsu", "anilist"], "tv": ["tmdb"]}


@dataclass
class SeriesSyncResult:
    status: str  # ok | error | skipped
    episodes: int = 0
    error: str | None = None


@dataclass
class RunSummary:
    updated: int = 0
    failed: int = 0
    skipped: int = 0
    errors: dict[str, str] = field(default_factory=dict)


def _episode_date(info: EpisodeInfo) -> date | None:
    if info.air_at is not None:
        return to_local_date(info.air_at)
    return info.air_date


def save_episodes(db: Session, series: Series, source: str, infos: list[EpisodeInfo]) -> None:
    existing = db.scalars(select(Episode).where(Episode.series_id == series.id)).all()
    by_external = {(e.source, e.external_id): e for e in existing}
    by_number = {
        (e.season_number or 1, e.episode_number): e
        for e in existing
        if e.episode_number is not None
    }
    for info in infos:
        episode = by_external.get((source, info.external_id))
        if episode is None and info.number is not None:
            # Fallback tra fonti diverse per non duplicare lo stesso episodio.
            episode = by_number.get((info.season_number or 1, info.number))
        new_date = _episode_date(info)
        if episode is None:
            episode = Episode(series_id=series.id, source=source, external_id=info.external_id)
            db.add(episode)
        elif episode.original_air_date != new_date:
            db.add(
                EpisodeDateChange(
                    episode_id=episode.id,
                    old_date=episode.original_air_date,
                    new_date=new_date,
                    source=source,
                )
            )
        episode.source = source
        episode.external_id = info.external_id
        episode.season_number = info.season_number
        episode.episode_number = info.number
        episode.title = info.title or episode.title
        episode.original_air_at = info.air_at
        episode.original_air_date = new_date
        db.flush()


def sync_series(
    db: Session, series: Series, providers: dict[str, CatalogProvider]
) -> SeriesSyncResult:
    ids = {e.source: e.external_id for e in series.external_ids}
    candidates = [s for s in EPISODE_SOURCES[series.kind] if s in ids]
    now = datetime.now(UTC)
    if not candidates:
        series.last_sync_status = "error"
        series.last_sync_error = "Nessuna fonte episodi disponibile"
        return SeriesSyncResult("error", error=series.last_sync_error)

    last_error: str | None = None
    for source in candidates:
        provider = providers[source]
        try:
            infos = provider.episodes(ids[source])
            if not series.synopsis or not series.start_date:
                details = provider.details(ids[source])
                series.synopsis = series.synopsis or details.synopsis
                series.start_date = series.start_date or details.start_date
                series.status = details.status or series.status
                series.year = series.year or (
                    details.start_date.year if details.start_date else None
                )
        except ProviderError as exc:
            last_error = f"{source}: {exc.message}"
            continue
        save_episodes(db, series, source, infos)
        series.last_synced_at = now
        series.last_sync_status = "ok"
        series.last_sync_error = None
        return SeriesSyncResult("ok", episodes=len(infos))

    # Errore: i dati precedenti restano, marcati come potenzialmente non aggiornati.
    series.last_sync_status = "error"
    series.last_sync_error = (last_error or "Errore sconosciuto")[:300]
    return SeriesSyncResult("error", error=series.last_sync_error)


def _finish(run: SyncRun, summary: RunSummary) -> None:
    run.completed_at = datetime.now(UTC)
    run.details = {
        "updated": summary.updated,
        "failed": summary.failed,
        "skipped": summary.skipped,
        "errors": summary.errors,
    }
    if summary.failed == 0:
        run.status = "succeeded"
    elif summary.updated > 0:
        run.status = "partial"
    else:
        run.status = "failed"
        run.error = next(iter(summary.errors.values()), "Aggiornamento fallito")[:500]


def claim_run(db: Session, run_id: uuid.UUID) -> bool:
    """Prende in carico un job in modo atomico: solo un worker passa da pending a running."""
    result = db.execute(
        update(SyncRun)
        .where(SyncRun.id == run_id, SyncRun.status == "pending")
        .values(status="running", started_at=datetime.now(UTC))
    )
    db.commit()
    return result.rowcount == 1  # type: ignore[attr-defined,no-any-return]


def execute_run(db: Session, run: SyncRun) -> None:
    summary = RunSummary()
    if run.kind == "series" and run.series_id:
        stmt = select(Series).where(Series.id == run.series_id)
    elif run.kind == "user" and run.user_id:
        stmt = select(Series).join(Following).where(Following.user_id == run.user_id)
    else:  # scheduled: tutte le serie seguite da qualcuno
        stmt = select(Series).where(Series.id.in_(select(Following.series_id)))
    series_list = db.scalars(stmt).all()

    with provider_registry() as providers:
        for series in series_list:
            try:
                result = sync_series(db, series, providers)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("sync failed for series %s", series.id)
                result = SeriesSyncResult("error", error="Errore interno")
            if result.status == "ok":
                summary.updated += 1
            else:
                summary.failed += 1
                summary.errors[str(series.id)] = result.error or "errore"

    _finish(run, summary)
    if run.kind == "user" and run.user_id and summary.failed == 0:
        user = db.get(User, run.user_id)
        if user:
            user.last_successful_sync_at = run.completed_at
    db.commit()


def enqueue_run(
    db: Session, kind: str, *, user_id: uuid.UUID | None = None, series_id: uuid.UUID | None = None
) -> SyncRun:
    run = SyncRun(kind=kind, user_id=user_id, series_id=series_id, status="pending", details={})
    db.add(run)
    db.commit()
    return run


def active_run(db: Session, **filters: object) -> SyncRun | None:
    stmt = select(SyncRun).where(SyncRun.status.in_(["pending", "running"]))
    for key, value in filters.items():
        stmt = stmt.where(getattr(SyncRun, key) == value)
    return db.scalars(stmt.limit(1)).first()


def last_run_at(db: Session, kind: str) -> datetime | None:
    return db.scalar(
        select(SyncRun.created_at)
        .where(SyncRun.kind == kind)
        .order_by(SyncRun.created_at.desc())
        .limit(1)
    )


def cooldown_remaining(db: Session, user_id: uuid.UUID, cooldown_seconds: int) -> int:
    latest = db.scalar(
        select(SyncRun.created_at)
        .where(SyncRun.user_id == user_id, SyncRun.kind == "user")
        .order_by(SyncRun.created_at.desc())
        .limit(1)
    )
    if latest is None:
        return 0
    remaining = latest + timedelta(seconds=cooldown_seconds) - datetime.now(UTC)
    return max(0, int(remaining.total_seconds()))
